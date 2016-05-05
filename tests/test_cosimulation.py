from tests.base_hdl_test import TestCase

from veriutils import *
from myhdl import (intbv, modbv, enum, Signal, ResetSignal, instance,
                   delay, always, always_seq, Simulation, StopSimulation,
                   always_comb, block, BlockError)

import unittest
import copy
from itertools import chain
from random import randrange

import os
import tempfile
import shutil

import mock

from veriutils import SynchronousTest, myhdl_cosimulation, random_source

from veriutils.tests.test_cosimulation import CosimulationTestMixin

from ovenbird import (
    VIVADO_EXECUTABLE, vivado_verilog_cosimulation, vivado_vhdl_cosimulation,
    VivadoError)


@block
def _broken_factory(test_input, test_output, reset, clock):
    
    @always_seq(clock.posedge, reset=reset)
    def broken_identity():
        test_output.next = test_input
    
    test_output.driven = 'reg'
    test_input.read = True

    _broken_factory.vhdl_code = '''
    garbage
    '''
    _broken_factory.verilog_code = '''
    garbage
    '''
    return broken_identity

class VivadoCosimulationFunctionTests(CosimulationTestMixin):
    # Common code for Vivado cosimulation tests.

    check_mocks = False

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory, 
                           args, arg_types, **kwargs):

        raise NotImplementedError

    def results_munger(self, premunged_results):
        return premunged_results # [1:]

    def construct_and_simulate(
        self, sim_cycles, dut_factory, ref_factory, args, arg_types, 
        **kwargs):

        if VIVADO_EXECUTABLE is None:
            raise unittest.SkipTest('Vivado executable not in path')

        return self.vivado_sim_wrapper(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

    def construct_simulate_and_munge(
        self, sim_cycles, dut_factory, ref_factory, args, arg_types, 
        **kwargs):
        
        if VIVADO_EXECUTABLE is None:
            raise unittest.SkipTest('Vivado executable not in path')

        dut_outputs, ref_outputs = self.construct_and_simulate(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

        # We've used an asynchronous reset, so the output will be undefined
        # at the first clock edge. Therefore we prune the first sample from
        # all the recorded values
        for each in arg_types:
            dut_outputs[each] = self.results_munger(dut_outputs[each])
            ref_outputs[each] = self.results_munger(ref_outputs[each])

        return dut_outputs, ref_outputs


    @unittest.skipIf(VIVADO_EXECUTABLE is None,
                     'Vivado executable not in path')
    def test_keep_tmp_files(self):
        '''It should be possible to keep the temporary files after simulation.
        '''
        sim_cycles = 30
        
        # This method is slightly flaky - it's quite implementation dependent
        # and may break if mkdtemp is imported into the namespace of
        # cosimulation rather than tempfile, or if multiple calls are
        # made to mkdtemp.
        import tempfile, sys
        orig_mkdtemp = tempfile.mkdtemp

        dirs = []
        def mkdtemp_wrapper():
            new_dir = orig_mkdtemp()
            dirs.append(new_dir)

            return new_dir

        try:
            tempfile.mkdtemp = mkdtemp_wrapper

            # We also want to drop the helpful output message to keep
            # the test clean.
            sys.stdout = open(os.devnull, "w")
            self.vivado_sim_wrapper(
                sim_cycles, self.identity_factory, self.identity_factory, 
                self.default_args, self.default_arg_types,
                keep_temp_files=True)
            
            self.assertTrue(os.path.exists(dirs[0]))

        finally:
            # clean up
            tempfile.mkdtemp = orig_mkdtemp
            sys.stdout = sys.__stdout__
            try:
                shutil.rmtree(dirs[0])
            except OSError:
                pass

    def test_missing_vivado_raises(self):
        '''Vivado missing from the path should raise an EnvironmentError.
        '''
        sim_cycles = 30

        existing_PATH = os.environ['PATH']
        import ovenbird
        existing_VIVADO_EXECUTABLE = ovenbird.VIVADO_EXECUTABLE
        ovenbird.VIVADO_EXECUTABLE = None
        try:
            os.environ['PATH'] = ''
            self.assertRaisesRegex(
                EnvironmentError, 'Vivado executable not in path',
                self.vivado_sim_wrapper, sim_cycles, 
                self.identity_factory, self.identity_factory, 
                self.default_args, self.default_arg_types)

        finally:
            os.environ['PATH'] = existing_PATH
            ovenbird.VIVADO_EXECUTABLE = existing_VIVADO_EXECUTABLE

    def test_interface_case(self):
        '''It should be possible to work with interfaces'''

        args = self.default_args.copy()

        min_val = -1000
        max_val = 1000

        class Interface(object):
            def __init__(self):
                # The attributes are sorted, so we need to run through
                # them in the correct order. 'a', 'b', 'c', 'd' is fine.
                self.a = Signal(intbv(0, min=min_val, max=max_val))
                self.b = Signal(intbv(0, min=min_val, max=max_val))
                self.c = Signal(intbv(0, min=0, max=max_val))                
                self.d = Signal(bool(0))

        @block
        def identity_factory(test_input, test_output, reset, clock):
            @always_seq(clock.posedge, reset=reset)
            def identity():
                test_output.a.next = test_input.a
                test_output.b.next = test_input.b
                test_output.c.next = test_input.c
                test_output.d.next = test_input.d

            return identity            

        args['test_input'] = Interface()
        args['test_output'] = Interface()

        sim_cycles = 31

        dut_results, ref_results = self.construct_simulate_and_munge(
            sim_cycles, identity_factory, identity_factory, 
            args, self.default_arg_types)

        for signal in dut_results:
            self.assertEqual(dut_results[signal], ref_results[signal])

    def test_signal_list_arg(self):
        '''It should be possible to work with lists of signals.

        If the list contains non-signals, they are ignored.
        '''

        args = self.default_args.copy()

        # We need to overwrite the parent implemented version in order
        # to create a test that will convert properly.
        N = 20
        n = 8
        input_signal_list = [
            Signal(intbv(0, min=-2**n, max=2**n-1)) for _ in range(1, N+1)]

        output_signal_list = [
            Signal(intbv(0, min=-2**n, max=2**n-1)) for _ in range(1, N+1)]

        @block
        def identity_factory(test_input, test_output, reset, clock):
            @always_seq(clock.posedge, reset=reset)
            def identity():
                for i in range(N):
                    test_output[i].next = test_input[i]

            return identity            

        args['test_input'] = input_signal_list
        args['test_output'] = output_signal_list

        sim_cycles = 31

        dut_results, ref_results = self.construct_simulate_and_munge(
            sim_cycles, identity_factory, identity_factory, 
            args, self.default_arg_types)

        for signal in dut_results:
            self.assertEqual(dut_results[signal][1:], ref_results[signal][1:])


class TestVivadoVHDLCosimulationFunction(VivadoCosimulationFunctionTests, 
                                         TestCase):
    '''There should be an alternative version of the cosimulation function
    that runs the device under test through the Vivado VHDL simulator.
    '''

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory, 
                           args, arg_types, **kwargs):

        return vivado_vhdl_cosimulation(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

    @unittest.skipIf(VIVADO_EXECUTABLE is None,
                     'Vivado executable not in path')
    def test_missing_hdl_file_raises(self):
        '''An EnvironmentError should be raised for a missing HDL file.

        If the settings stipulate a HDL file should be included, but it 
        is not there, an EnvironmentError should be raised.
        '''
        self.identity_factory.vhdl_dependencies = ['a_missing_file.vhd']
        sim_cycles = 10
        self.assertRaisesRegex(
            EnvironmentError, 'An expected HDL file is missing', 
            self.vivado_sim_wrapper, sim_cycles, self.identity_factory, 
            self.identity_factory, self.default_args, self.default_arg_types)

    @unittest.skipIf(VIVADO_EXECUTABLE is None,
                     'Vivado executable not in path')
    def test_vivado_VHDL_error_raises(self):
        '''Errors with VHDL code in Vivado should raise a RuntimeError.
        '''
        sim_cycles = 30

        self.assertRaisesRegex(
            VivadoError, 'Error running the Vivado VHDL simulator',
            self.vivado_sim_wrapper, sim_cycles, 
            _broken_factory, self.identity_factory, 
            self.default_args, self.default_arg_types)

class TestVivadoVerilogCosimulationFunction(VivadoCosimulationFunctionTests, 
                                            TestCase):
    '''There should be an alternative version of the cosimulation function
    that runs the device under test through the Vivado verilog simulator.
    '''

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory, 
                           args, arg_types, **kwargs):

        return vivado_verilog_cosimulation(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

    @unittest.skipIf(VIVADO_EXECUTABLE is None,
                     'Vivado executable not in path')
    def test_missing_hdl_file_raises(self):
        '''An EnvironmentError should be raised for a missing HDL file.

        If the settings stipulate a HDL file should be included, but it 
        is not there, an EnvironmentError should be raised.
        '''
        self.identity_factory.verilog_dependencies = ['a_missing_file.v']
        sim_cycles = 10
        self.assertRaisesRegex(
            EnvironmentError, 'An expected HDL file is missing', 
            self.vivado_sim_wrapper, sim_cycles, self.identity_factory, 
            self.identity_factory, self.default_args, self.default_arg_types)

    @unittest.skipIf(VIVADO_EXECUTABLE is None,
                     'Vivado executable not in path')
    def test_vivado_verilog_error_raises(self):
        '''Errors with Verilog code in Vivado should raise a RuntimeError.
        '''
        sim_cycles = 30

        self.assertRaisesRegex(
            VivadoError, 'Error running the Vivado Verilog simulator',
            self.vivado_sim_wrapper, sim_cycles, 
            _broken_factory, self.identity_factory, 
            self.default_args, self.default_arg_types)
