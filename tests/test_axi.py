from veriutils.tests.test_axi_stream import TestAxiMasterPlaybackBlockMinimal
from ovenbird import vivado_verilog_cosimulation, vivado_vhdl_cosimulation

class TestAxiMasterPlaybackBlockMinimalVivadoVHDL(
    TestAxiMasterPlaybackBlockMinimal):
    def sim_wrapper(self, sim_cycles, dut_factory, ref_factory,
                           args, arg_types, **kwargs):

        return vivado_vhdl_cosimulation(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

class TestAxiMasterPlaybackBlockMinimalVivadoVerilog(
    TestAxiMasterPlaybackBlockMinimal):
    def sim_wrapper(self, sim_cycles, dut_factory, ref_factory,
                           args, arg_types, **kwargs):

        return vivado_verilog_cosimulation(
            sim_cycles, dut_factory, ref_factory, args, arg_types, **kwargs)

