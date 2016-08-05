from myhdl import *

from unittest import TestCase

from ovenbird import *


class VivadoVectorOr(VivadoIP):

    def __init__(self):
        port_mappings = {
            'in_A': (intbv(0)[8:], PortDirection.input, 'Op1'),
            'in_B': (intbv(0)[8:], PortDirection.input, 'Op2'),
            'output': (intbv(0)[8:], PortDirection.output, 'res')}

        config = {'c_size': '8',
                  'c_operation': 'or'}

        entity_name = 'vector_or'
        ports = port_mappings
        ip_name = 'util_vector_logic'
        vendor = 'xilinx.com'
        library = 'ip'
        version = '2.0'

        VivadoIP.__init__(
            self, entity_name, port_mappings, ip_name, vendor, library,
            version, config)


@block
def comb_vector_or(in_A, in_B, output, ip_factory):

    length = len(in_A)

    @always_comb
    def vector_or():
        for n in range(length):
            output.next[n] = in_A[n] or in_B[n]

    comb_vector_or.verilog_code = ip_factory.get_verilog_instance()
    comb_vector_or.vhdl_code = ip_factory.get_vhdl_instance()

    in_A.read = True
    in_B.read = True
    output.driven = 'wire'

    return vector_or

@block
def comb_vector_or_with_port_mappings(
    A, B, output, ip_factory, port_mappings):
    '''We change the signal names here to unmap from the expected in_A and
    in_B so port_mappings can do its thing.
    '''
    length = len(A)

    @always_comb
    def vector_or():
        for n in range(length):
            output.next[n] = A[n] or B[n]

    comb_vector_or_with_port_mappings.verilog_code = (
        ip_factory.get_verilog_instance(**port_mappings))
    comb_vector_or_with_port_mappings.vhdl_code = (
        ip_factory.get_vhdl_instance(**port_mappings))

    A.read = True
    B.read = True
    output.driven = 'wire'

    return vector_or

@block
def clocked_vector_or(clock, in_A, in_B, output, ip_factory,
                      port_mappings=None):

    internal_sig = Signal(intbv(0)[len(in_A):])

    @always(clock.posedge)
    def clocked_or():
        output.next = internal_sig

    clock.read = True

    if port_mappings is None:
        comb_or = comb_vector_or(in_A, in_B, internal_sig, ip_factory)
    else:
        comb_or = comb_vector_or_with_port_mappings(
            in_A, in_B, internal_sig, ip_factory, port_mappings)

    return clocked_or, comb_or

class VivadoIPTests(object):

    def setUp(self):
        self.ip_factory = VivadoVectorOr()

        self.args = {
            'in_A': Signal(intbv(0)[8:]), 'in_B': Signal(intbv(0)[8:]),
            'output': Signal(intbv(0)[8:]), 'clock': Signal(False),
            'ip_factory': self.ip_factory}

        self.arg_types = {
            'in_A': 'random', 'in_B': 'random', 'output': 'output',
            'clock': 'clock', 'ip_factory': 'non-signal'}

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory,
                           args, arg_types, **kwargs):

        raise NotImplementedError

    def test_basic(self):
        '''The IP block should return the same as the reference block.
        '''

        dut_results, ref_results = self.vivado_sim_wrapper(
            10, clocked_vector_or, clocked_vector_or, self.args,
            self.arg_types)

        self.assertEqual(dut_results, ref_results)

    def test_basic_with_port_mappings(self):
        '''The IP block should return the same as the reference block when
        the port_mappings arguments are used
        '''
        self.args = {
            'in_A': Signal(intbv(0)[8:]), 'in_B': Signal(intbv(0)[8:]),
            'output': Signal(intbv(0)[8:]), 'clock': Signal(False),
            'ip_factory': self.ip_factory}

        port_mappings = {'in_A': 'A', 'in_B': 'B'}

        self.args['port_mappings'] = port_mappings

        self.arg_types = {
            'in_A': 'random', 'in_B': 'random', 'output': 'output',
            'clock': 'clock', 'ip_factory': 'non-signal',
            'port_mappings': 'non-signal'}

        dut_results, ref_results = self.vivado_sim_wrapper(
            10, clocked_vector_or, clocked_vector_or, self.args,
            self.arg_types)

        self.assertEqual(dut_results, ref_results)


class TestVivadoVerilogCosimulationFunction(VivadoIPTests, TestCase):
    '''There should be an alternative version of the cosimulation function
    that runs the device under test through the Vivado verilog simulator.
    '''

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory,
                           args, arg_types, **kwargs):

        return vivado_verilog_cosimulation(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

class TestVivadoVHDLCosimulationFunction(VivadoIPTests, TestCase):
    '''There should be an alternative version of the cosimulation function
    that runs the device under test through the Vivado verilog simulator.
    '''

    def vivado_sim_wrapper(self, sim_cycles, dut_factory, ref_factory,
                           args, arg_types, **kwargs):

        return vivado_vhdl_cosimulation(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)
