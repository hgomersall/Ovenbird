from tests.base_hdl_test import TestCase

from veriutils import *
from myhdl import (intbv, modbv, enum, Signal, ResetSignal, instance,
                   delay, always, always_seq, Simulation, StopSimulation,
                   always_comb, block, BlockError, ConversionError)

import unittest
import copy
from itertools import chain
from random import randrange

import os
import tempfile
import shutil

import mock

from veriutils import SynchronousTest, myhdl_cosimulation, random_source

from veriutils.tests.test_convertible import ConvertibleCodeTestsMixin

from ovenbird import (
    VIVADO_EXECUTABLE, vivado_verilog_cosimulation, vivado_vhdl_cosimulation,
    VivadoError, OvenbirdConversionError)


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

class VivadoCosimulationFunctionTests(ConvertibleCodeTestsMixin):
    # Common code for Vivado cosimulation tests.

    check_mocks = False

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory,
                           args, arg_types, **kwargs):

        raise NotImplementedError

    def construct_and_simulate(
        self, sim_cycles, dut_factory, ref_factory, args, arg_types,
        **kwargs):

        if VIVADO_EXECUTABLE is None:
            raise unittest.SkipTest('Vivado executable not in path')

        return self.vivado_sim_wrapper(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

    @unittest.expectedFailure
    def test_conversion_error_of_user_code(self):
        '''Conversion errors of user code should be presented to the user
        as a ConversionError.
        '''
        # FIXME this test fails because of funny stateful issues in myhdl
        # conversion when convert is used more than once
        @block
        def failure_block(clock, input_signal, output_signal):

            @always(clock.posedge)
            def driver1():
                output_signal.next = input_signal

            @always(clock.posedge)
            def driver2():
                output_signal.next = input_signal

            return driver1, driver2

        args = {'clock': Signal(False),
                'input_signal': Signal(False),
                'output_signal': Signal(False)}

        arg_types = {'clock': 'clock',
                     'input_signal': 'custom',
                     'output_signal': 'output'}

        with self.assertRaises(ConversionError) as cm:
            self.vivado_sim_wrapper(
                10, failure_block, failure_block, args, arg_types)

        # Make sure the asserion is exactly a ConversionError
        self.assertIs(type(cm.exception), ConversionError)

    def test_conversion_error_of_veriutils_convertible_top(self):
        '''Conversion errors of the veriutils convertible top should be
        presented as an OvenbirdConversionError.
        '''
        @block
        def convertible_block(clock, input_signal, output_signal):

            @always(clock.posedge)
            def driver():
                output_signal.next = input_signal

            return driver

        args = {'clock': Signal(False),
                'input_signal': Signal(False),
                'output_signal': Signal(False)}

        arg_types = {'clock': 'clock',
                     'input_signal': 'custom',
                     'output_signal': 'custom'}

        self.assertRaises(OvenbirdConversionError, self.vivado_sim_wrapper,
                          10, convertible_block, convertible_block,
                          args, arg_types)


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
