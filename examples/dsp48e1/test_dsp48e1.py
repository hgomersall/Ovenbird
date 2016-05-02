
import unittest
from tests.base_hdl_test import HDLTestCase, get_signed_intbv_rand_signal
from .utils import weighted_random_reset_source
from myhdl import (intbv, enum, Signal, ResetSignal, instance, block,
                   delay, always, always_seq, Simulation, StopSimulation)

from random import randrange
import random

from collections import deque

from .dsp48e1 import (
    DSP48E1, DSP48E1_OPMODE_MULTIPLY, DSP48E1_OPMODE_MULTIPLY_ADD, 
    DSP48E1_OPMODE_MULTIPLY_ACCUMULATE,
    DSP48E1_OPMODE_MULTIPLY_DECCUMULATE)

from veriutils import (
    myhdl_cosimulation, copy_signal)
    
from ovenbird import (
    vivado_vhdl_cosimulation, vivado_verilog_cosimulation, VIVADO_EXECUTABLE)

PERIOD = 10

class DSP48E1TestCase(HDLTestCase):
    
    def setUp(self):
        
        self.len_A = 25
        self.len_B = 18
        self.len_C = 48
        self.len_P = 48

        self.clock = Signal(bool(1))
        self.clock_enable = Signal(bool(1))        
        self.reset = ResetSignal(bool(0), active=1, async=False)

        self.A, self.a_min, self.a_max = (
            get_signed_intbv_rand_signal(self.len_A))
        self.B, self.b_min, self.b_max = (
            get_signed_intbv_rand_signal(self.len_B))

        initial_C, _c_min, _c_max = (
            get_signed_intbv_rand_signal(self.len_C))

        # Reduce the range of C, but not enough to reduce its bitwidth
        self.c_min = int(_c_min * 0.6)
        self.c_max = int(_c_max * 0.6)
        self.C = Signal(intbv(0, min=self.c_min, max=self.c_max))
        self.C.val[:] = int(initial_C.val * 0.6)

        self.P, self.p_min, self.p_max = (
            get_signed_intbv_rand_signal(self.len_P))

        # Tweak the initialisations
        self.P.val[:] = 0

        self.operations = {
            'multiply': DSP48E1_OPMODE_MULTIPLY,
            'multiply_add': DSP48E1_OPMODE_MULTIPLY_ADD,
            'multiply_accumulate': DSP48E1_OPMODE_MULTIPLY_ACCUMULATE,
            'multiply_deccumulate': DSP48E1_OPMODE_MULTIPLY_DECCUMULATE
        }

        self.opmode = Signal(intbv(0, min=0, max=len(self.operations)))

        self.default_args = {
            'A': self.A, 'B': self.B, 'C': self.C, 'P': self.P,
            'opmode': self.opmode, 'reset': self.reset, 'clock': self.clock, 
            'clock_enable': self.clock_enable}

        self.default_arg_types = {
            'A': 'random', 'B': 'random', 'C': 'random', 'P': 'output', 
            'opmode': 'custom', 'reset': 'init_reset', 'clock': 'clock', 
            'clock_enable': 'custom'}

        # Should work, no probs
        test = DSP48E1(**self.default_args)

        self.pipeline_registers = 3

class TestDSP48E1Interface(DSP48E1TestCase):
    '''The DSP48E1 should have a well defined interface, with careful
    checking of the parameters.
    '''

    def test_A_port_checked(self):
        '''The A port should be an 25 bit signed intbv.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_intbv_test(DSP48E1, 'A', 25, signed=True)

    def test_B_port_checked(self):
        '''The B port should be an 18 bit signed intbv.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_intbv_test(DSP48E1, 'B', 18, signed=True)

    def test_C_port_checked(self):
        '''The C port should be an 48 bit signed intbv.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_intbv_test(DSP48E1, 'C', 48, signed=True)

    def test_P_port_checked(self):
        '''The P port should be an 48 bit signed intbv.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_intbv_test(DSP48E1, 'P', 48, signed=True)

    def test_opmode_port_checked(self):
        '''The opmode port should be an unsigned intbv.

        The min and max values of the opmode port should be determined by 
        the number of implemented opmodes.
        '''
        opmode_range = (self.opmode.min, self.opmode.max)
        self.do_port_check_intbv_test(DSP48E1, 'opmode', 
                                      val_range=opmode_range)

    def test_clock_port_checked(self):
        '''The clock port should be a boolean signal.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_bool_test(DSP48E1, 'clock')

    def test_clock_enable_port_checked(self):
        '''The clock enable port should be a boolean signal.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_bool_test(DSP48E1, 'clock_enable')

    def test_reset_port_checked(self):
        '''The reset port should be a boolean signal.

        Anything else should raise a ValueError.
        '''
        self.do_port_check_reset_test(DSP48E1, 'reset', active=1, async=False)

class TestDSP48E1Simulation(DSP48E1TestCase):
    '''The DSP48E1 slice should implement various bits of functionality that
    should be verifiable through simulation.
    '''

    def cosimulate(self, sim_cycles, dut_factory, ref_factory, args, 
                   arg_types, **kwargs):

        return myhdl_cosimulation(sim_cycles, dut_factory, ref_factory, 
                                  args, arg_types, **kwargs)

    def test_basic_multiply(self):
        '''The basic multiply with default Z should be the product of A and B.
        '''

        reset = self.default_args['reset']
        clock = self.default_args['clock']
        @block
        def set_opmode():
            @always_seq(clock.posedge, reset=reset)
            def _set_opmode():
                self.opmode.next = self.operations['multiply']

            return _set_opmode
        
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

        cycles = 20
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types, 
            custom_sources=[(set_opmode, (), {})])

        # There are pipeline_registers cycles latency on the output. 
        # The reference above has only 1 cycle latency, so we need to offset 
        # the results by pipeline_registers - 1 cycles.
        self.assertEqual(dut_outputs['P'][self.pipeline_registers - 1:], 
                         ref_outputs['P'][:-(self.pipeline_registers - 1)])

    def test_multiply_add(self):
        '''There should be a multiply-add mode, giving C + A * B
        '''
        reset = self.default_args['reset']
        clock = self.default_args['clock']
        @block
        def set_opmode():
            @always_seq(clock.posedge, reset=reset)
            def _set_opmode():
                self.opmode.next = self.operations['multiply_add']

            return _set_opmode

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            C = kwargs['C']            
            clock = kwargs['clock']
            reset = kwargs['reset']

            @always_seq(clock.posedge, reset=reset)
            def test_basic_multiply():
                P.next = A * B + C

            return test_basic_multiply

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        cycles = 20
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types,
            custom_sources=[(set_opmode, (), {})])

        # There are pipeline_registers cycles latency on the output. 
        # The reference above has only 1 cycle latency, so we need to offset 
        # the results by pipeline_registers - 1 cycles.

        self.assertEqual(dut_outputs['P'][self.pipeline_registers - 1:], 
                         ref_outputs['P'][:-(self.pipeline_registers - 1)])


    def test_multiply_accumulate(self):
        '''There should be a multiply-accumulate mode, giving P + A * B.

        P is defined to be the output, which is not pipelined. That is,
        the output should always be incremented by A*B as long as the 
        multiply-accumulate is ongoing.
        '''
        reset = self.default_args['reset']
        clock = self.default_args['clock']

        @block
        def set_opmode():
            @always_seq(clock.posedge, reset=reset)
            def _set_opmode():
                self.opmode.next = self.operations['multiply_accumulate']

            return _set_opmode

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            clock = kwargs['clock']
            reset = kwargs['reset']

            @always_seq(clock.posedge, reset=reset)
            def test_basic_multiply():
                P.next = P + A * B

            return test_basic_multiply

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        # Don't run too many cycles or you'll get an overflow!
        cycles = 20
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types,
            custom_sources=[(set_opmode, (), {})])

        # There are pipeline_registers cycles latency on the output. 
        # The reference above has only 1 cycle latency, so we need to offset 
        # the results by pipeline_registers - 1 cycles.
        self.assertEqual(dut_outputs['P'][self.pipeline_registers - 1:], 
                         ref_outputs['P'][:-(self.pipeline_registers - 1)])

    def test_multiply_deccumulate(self):
        '''There should be a multiply-deccumulate mode, giving P - A * B.

        P is defined to be the output, which is not pipelined. That is,
        the output should be negated on every cycle and then incremented by 
        A*B as long as the multiply-deccumulate is ongoing.
        '''
        reset = self.default_args['reset']
        clock = self.default_args['clock']

        @block
        def set_opmode():
            @always_seq(clock.posedge, reset=reset)
            def _set_opmode():
                self.opmode.next = self.operations['multiply_deccumulate']

            return _set_opmode

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            clock = kwargs['clock']
            reset = kwargs['reset']

            @always_seq(clock.posedge, reset=reset)
            def test_basic_multiply():

                P.next = P - A * B

            return test_basic_multiply

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        # Don't run too many cycles or you'll get an overflow!
        cycles = 20
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types,
            custom_sources=[(set_opmode, (), {})])

        # There are pipeline_registers cycles latency on the output. 
        # The reference above has only 1 cycle latency, so we need to offset 
        # the results by pipeline_registers - 1 cycles.
        self.assertEqual(dut_outputs['P'][self.pipeline_registers - 1:], 
                         ref_outputs['P'][:-(self.pipeline_registers - 1)])

    def test_clock_enable(self):
        '''clock_enable False should stop the pipeline being stepped.

        When clock_enable is False, the DSP48E1 should remain in an unchanged
        state until it is True again, unless the reset signal is active.
        '''
        reset = self.default_args['reset']
        clock = self.default_args['clock']

        operation = self.operations['multiply']

        @block
        def set_opmode():
            @always_seq(clock.posedge, reset=reset)
            def _set_opmode():
                self.opmode.next = operation

            return _set_opmode

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            opmode = kwargs['opmode']
            clock_enable = kwargs['clock_enable']            
            clock = kwargs['clock']
            reset = kwargs['reset']

            # Each pipeline should be pipeline_registers - 1 long since
            # there is one implicit register.
            A_pipeline = deque(
                [copy_signal(A) for _ in range(self.pipeline_registers - 1)])
            B_pipeline = deque(
                [copy_signal(B) for _ in range(self.pipeline_registers - 1)])
            opmode_pipeline = deque(
                [copy_signal(opmode) for _ in 
                 range(self.pipeline_registers - 1)])

            @always(clock.posedge)
            def test_arbitrary_pipeline():
                
                if reset == reset.active:
                    for _A, _B, _opmode in zip(
                        A_pipeline, B_pipeline, opmode_pipeline):

                        _A.next = _A._init
                        _B.next = _B._init
                        _opmode.next = _opmode._init
                    
                    P.next = P._init

                else:

                    if clock_enable:
                        A_pipeline.append(copy_signal(A))
                        B_pipeline.append(copy_signal(B))
                        opmode_pipeline.append(copy_signal(opmode))

                        A_out = A_pipeline.popleft()
                        B_out = B_pipeline.popleft()
                        opmode_out = opmode_pipeline.popleft()
                        
                        P.next = A_out * B_out
                    else:
                        # Nothing changes
                        pass

            return test_arbitrary_pipeline

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        arg_types['clock_enable'] = 'random'

        # Don't run too many cycles or you'll get an overflow!
        cycles = 40
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types,
            custom_sources=[(set_opmode, (), {})])

        self.assertEqual(dut_outputs['P'], ref_outputs['P'])

    def test_reset_trumps_clock_enable(self):
        '''If reset is active then clock enable is ignored; the reset occurs.

        The reset should always happen if reset is active on a clock edge.
        '''
        reset = self.default_args['reset']
        clock = self.default_args['clock']

        operation = self.operations['multiply']

        @block
        def set_opmode():
            @always_seq(clock.posedge, reset=reset)
            def _set_opmode():
                self.opmode.next = operation

            return _set_opmode

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            opmode = kwargs['opmode']
            clock_enable = kwargs['clock_enable']            
            clock = kwargs['clock']
            reset = kwargs['reset']

            # Each pipeline should be pipeline_registers - 1 long since
            # there is one implicit register.
            A_pipeline = deque(
                [copy_signal(A) for _ in range(self.pipeline_registers - 1)])
            B_pipeline = deque(
                [copy_signal(B) for _ in range(self.pipeline_registers - 1)])
            opmode_pipeline = deque(
                [copy_signal(opmode) for _ in 
                 range(self.pipeline_registers - 1)])

            @always(clock.posedge)
            def test_arbitrary_pipeline():
                
                if reset == reset.active:
                    for _A, _B, _opmode in zip(
                        A_pipeline, B_pipeline, opmode_pipeline):

                        _A.next = _A._init
                        _B.next = _B._init
                        _opmode.next = _opmode._init
                        P.next = P._init
                else:

                    if clock_enable:
                        A_pipeline.append(copy_signal(A))
                        B_pipeline.append(copy_signal(B))
                        opmode_pipeline.append(copy_signal(opmode))

                        A_out = A_pipeline.popleft()
                        B_out = B_pipeline.popleft()
                        opmode_out = opmode_pipeline.popleft()
                        
                        P.next = A_out * B_out
                    else:
                        # Nothing changes
                        pass

            return test_arbitrary_pipeline

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        arg_types.update({'reset': 'custom_reset',
                          'clock_enable': 'random'})

        custom_sources = [
            (weighted_random_reset_source, 
             (args['reset'], args['clock'], 0.7), {})]

        # Don't run too many cycles or you'll get an overflow!
        cycles = 40
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types, 
            custom_sources=custom_sources+[(set_opmode, (), {})])

        self.assertEqual(dut_outputs['reset'], ref_outputs['reset'])
        self.assertEqual(dut_outputs['P'], ref_outputs['P'])

    def test_changing_modes(self):
        '''It should be possible to change modes dynamically.

        When the mode is changed, the mode should propagate through the
        pipeline with the data. That is, the mode should be attached to
        the input it accompanies.
        '''
        
        # Create the (unique) reverse lookup
        opmode_reverse_lookup = {
            self.operations[key]: key for key in self.operations}

        @block
        def custom_reset_source(driven_reset, clock):
            dummy_reset = ResetSignal(bool(0), active=1, async=False)

            @instance
            def custom_reset():
                driven_reset.next = 1
                yield(clock.posedge)
                driven_reset.next = 1
                yield(clock.posedge)
                while True:
                    next_reset = randrange(0, 100)
                    # Be false 90% of the time.
                    if next_reset > 90:
                        driven_reset.next = 1
                    else:
                        driven_reset.next = 0
                        
                    yield(clock.posedge)

            return custom_reset

        @block
        def ref(**kwargs):

            P = kwargs['P']
            A = kwargs['A']
            B = kwargs['B']
            C = kwargs['C']            
            opmode = kwargs['opmode']
            clock_enable = kwargs['clock_enable']            
            clock = kwargs['clock']
            reset = kwargs['reset']

            # Each pipeline should be pipeline_registers - 1 long since
            # there is one implicit register.
            A_pipeline = deque(
                [copy_signal(A) for _ in range(self.pipeline_registers - 1)])
            B_pipeline = deque(
                [copy_signal(B) for _ in range(self.pipeline_registers - 1)])
            C_pipeline = deque(
                [copy_signal(C) for _ in range(self.pipeline_registers - 1)])
            opmode_pipeline = deque(
                [copy_signal(opmode) for _ in 
                 range(self.pipeline_registers - 1)])

            @always(clock.posedge)
            def test_arbitrary_pipeline():
                
                if reset == reset.active:
                    for _A, _B, _C, _opmode in zip(
                        A_pipeline, B_pipeline, C_pipeline, opmode_pipeline):

                        _A.next = _A._init
                        _B.next = _B._init
                        _C.next = _C._init
                        _opmode.next = _opmode._init
                        P.next = P._init
                else:

                    if clock_enable:
                        A_pipeline.append(copy_signal(A))
                        B_pipeline.append(copy_signal(B))
                        C_pipeline.append(copy_signal(C))
                        opmode_pipeline.append(copy_signal(opmode))

                        A_out = A_pipeline.popleft()
                        B_out = B_pipeline.popleft()
                        C_out = C_pipeline.popleft()
                        opmode_out = opmode_pipeline.popleft()
                        
                        if (opmode_reverse_lookup[int(opmode_out.val)] == 
                            'multiply'):
                            P.next = A_out * B_out

                        elif (opmode_reverse_lookup[int(opmode_out.val)] == 
                              'multiply_add'):
                            P.next = A_out * B_out + C_out

                        elif (opmode_reverse_lookup[int(opmode_out.val)] == 
                            'multiply_accumulate'):
                            P.next = P + A_out * B_out

                        elif (opmode_reverse_lookup[int(opmode_out.val)] == 
                            'multiply_deccumulate'):
                            P.next = P - A_out * B_out


            return test_arbitrary_pipeline

        args = self.default_args.copy()
        arg_types = self.default_arg_types.copy()

        arg_types.update({'opmode': 'random',
                          'clock_enable': 'random',
                          'reset': 'custom_reset'})

        custom_sources = [
            (custom_reset_source, (args['reset'], args['clock']), {})]

        cycles = 100
        dut_outputs, ref_outputs = self.cosimulate(
            cycles, DSP48E1, ref, args, arg_types, 
            custom_sources=custom_sources)

        self.assertEqual(dut_outputs['reset'], ref_outputs['reset'])   
        self.assertEqual(dut_outputs['P'], ref_outputs['P'])

@unittest.skipIf(VIVADO_EXECUTABLE is None, 'Vivado executable not in path')
class TestDSP48E1VivadoVHDLSimulation(TestDSP48E1Simulation):
    '''The tests of TestDSP48E1Simulation should run under the Vivado 
    simulator using VHDL.
    '''

    def cosimulate(self, sim_cycles, dut_factory, ref_factory, args, 
                   arg_types, **kwargs):

        return vivado_vhdl_cosimulation(sim_cycles, dut_factory, ref_factory, 
                                        args, arg_types, **kwargs)


@unittest.skipIf(VIVADO_EXECUTABLE is None, 'Vivado executable not in path')
class TestDSP48E1VivadoVerilogSimulation(TestDSP48E1Simulation):
    '''The tests of TestDSP48E1Simulation should run under the Vivado 
    simulator using VHDL.
    '''

    def cosimulate(self, sim_cycles, dut_factory, ref_factory, args, 
                   arg_types, **kwargs):

        return vivado_verilog_cosimulation(
            sim_cycles, dut_factory, ref_factory, 
            args, arg_types, **kwargs)
