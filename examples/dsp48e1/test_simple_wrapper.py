
from .simple_wrapper import SimpleWrapper
from .test_dsp48e1 import DSP48E1TestCase

import unittest

from myhdl import always_seq, block
from veriutils import myhdl_cosimulation
from ovenbird import vivado_vhdl_cosimulation, VIVADO_EXECUTABLE

class TestSimpleWrapperSimulation(DSP48E1TestCase):
    '''Test that wrapping a somewhat non-trivial object works fine.
    '''
    def cosimulate(self, sim_cycles, dut_factory, ref_factory, args,
                   arg_types, **kwargs):

        return myhdl_cosimulation(sim_cycles, dut_factory, ref_factory,
                                  args, arg_types, **kwargs)

    def test_basic_multiply(self):
        '''The basic multiply should be the product of A and B.
        '''

        self.opmode.val[:] = self.operations['multiply']

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            clock = kwargs['clock']
            reset = kwargs['reset']

            @always_seq(clock.posedge, reset=reset)
            def test_basic_multiply():
                P.next = A * B

            return test_basic_multiply

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        # Get rid of unnecessary args
        del args['C']
        del arg_types['C']
        del args['opmode']
        del arg_types['opmode']

        cycles = 20
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, SimpleWrapper, ref, args, arg_types)

        # There are pipeline_registers cycles latency on the output.
        # The reference above has only 1 cycle latency, so we need to offset
        # the results by pipeline_registers - 1 cycles.
        self.assertEqual(dut_outputs['P'][self.pipeline_registers - 1:],
                         ref_outputs['P'][:-(self.pipeline_registers - 1)])

@unittest.skipIf(VIVADO_EXECUTABLE is None, 'Vivado executable not in path')
class TestSimpleWrapperVivadoSimulation(TestSimpleWrapperSimulation):
    '''The tests of TestDSP48E1Simulation should run under the Vivado
    simulator with VHDL.
    '''

    def cosimulate(self, sim_cycles, dut_factory, ref_factory, args,
                   arg_types, **kwargs):

        return vivado_vhdl_cosimulation(sim_cycles, dut_factory, ref_factory,
                                        args, arg_types, **kwargs)

