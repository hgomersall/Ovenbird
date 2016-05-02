
'''A module implementing the Xilinx DSP48E1 DSP slice, making use of the
VivadoIP block.
'''

from myhdl import (
    always_seq, always_comb, Signal, intbv, enum, ConcatSignal, block)
from veriutils import (
    check_intbv_signal, check_bool_signal, check_reset_signal)
from math import log, floor

# The two bits we need from ovenbird in this example are VivadoIP and 
# PortDirection
from ovenbird import VivadoIP, PortDirection

# We firstly define a few constants specific to _this_ example, but not 
# relevant to understanding VivadoIP.

# Opmode enumeration
N_DSP48E1_OPMODES = 4
DSP48E1_OPMODE_MULTIPLY = 0
DSP48E1_OPMODE_MULTIPLY_ADD = 1
DSP48E1_OPMODE_MULTIPLY_ACCUMULATE = 2
DSP48E1_OPMODE_MULTIPLY_DECCUMULATE = 3 # deccumulate means to subtract from P

# Set the values for the internal multiplexers
X_ZEROS, X_M = 0, 1
Y_ZEROS, Y_M = 0, 1
Z_ZEROS, Z_P, Z_C = 0, 2, 3

class VivadoDSPMacro(VivadoIP):
    '''An instance of the
    '''

    def __init__(self):
        # In this example, the class takes no construction arguments.
        #
        # Having arguments is perfectly fine and is a good way to configure
        # the IP at run time, should that be desired.

        # The parent class __init__ is called with the following arguments
        # defined. These fully describe the IP to be instantiated and 
        # (hopefully) are as flexible as instantiation inside Vivado.

        # port_mappings gives the mapping from signal names (which most easily 
        # should be the same as those used by the subsequent MyHDL block, 
        # though this can be updated when the instance is created) to 
        # a tuple containing the MyHDL signal type, the signal direction and 
        # the respective name that the IP block uses for the signal.
        #
        # The type is set using a valid MyHDL type, as follows. The length
        # of the bit vector should agree with that mandated by the created
        # IP block. In the case of VHDL, the signal is cast to std_logic or
        # std_logic_vector at conversion time.
        # 
        # The port direction is set by the PortDirection enumeration (input
        # or output).
        #
        # The IP block signal name is simply a string and should agree with
        # the documentation.
        port_mappings = {
            'A': (intbv(0, min=-(2**24-1), max=(2**24)), 
                  PortDirection.input, 'A'),
            'B': (intbv(0, min=-(2**17-1), max=(2**17)), 
                  PortDirection.input, 'B'),
            'C': (intbv(0, min=-(2**47-1), max=(2**47)), 
                  PortDirection.input, 'C'),
            'P': (intbv(0, min=-(2**47-1), max=(2**47)), 
                  PortDirection.output, 'P'),
            'opmode': (intbv(0)[2:], PortDirection.input, 'SEL'),
            'reset': (intbv(0)[1:], PortDirection.input, 'SCLR'),
            'clock': (intbv(0)[1:], PortDirection.input, 'CLK'),
            'clock_enable': (intbv(0)[1:], PortDirection.input, 'CE')}
        
        # config is the meat of describing the IP block. Each key corresponds
        # to a CONFIG option on the macro.
        # The options should be described in the IP block documentation, 
        # but the easiest way of working out the options is to create 
        # an instance of the IP block in a dummy project (either with a 
        # block diagram or through the IP Catalog) and then inspect that
        # instance through the tcl console.
        # 
        # 
        # It's possible to see what happens when you twiddle parameters in
        # the Vivado IP GUI by observing the tcl console and what CONFIG
        # values are changed.
        #
        # If using a block diagram to inspect the IP block, get a list of the 
        # valid options with:
        # list_property [get_bd_cells ip_instance_name]
        # or
        # report_property [get_bd_cells ip_instance_name] to get more
        # information.
        # 
        # If you're using the IP Catalog to twiddle the ip, then use
        # get_ips instead of get_bd_cells.
        #
        # Since all these values and keys are just strings, they can be
        # configured programatically based on arguments to this class
        # instance. This allows a huge amount of flexibility in interacting
        # with the IP framework in Vivado.
        config = {'instruction1': 'A*B',
                  'instruction2': 'A*B+C',
                  'instruction3': 'P+A*B',
                  'instruction4': 'P-A*B',
                  'pipeline_options': 'Expert',
                  'areg_3': 'false',
                  'breg_3': 'false',
                  'creg_3': 'false',
                  'opreg_3': 'false',
                  'has_ce': 'true',
                  'has_sclr': 'true',
                  'areg_4': 'true',
                  'breg_4': 'true',
                  'creg_4': 'true',
                  'creg_5': 'true',
                  'opreg_4': 'true',
                  'opreg_5': 'true',
                  'mreg_5': 'true',
                  'preg_6': 'true',
                  'a_width': '25',
                  'a_binarywidth': '0',
                  'b_width': '18',
                  'b_binarywidth': '0',
                  'c_width': '48',
                  'c_binarywidth': '0',
                  'pcin_binarywidth': '0',
                  'p_full_width': '48',
                  'p_width': '48',
                  'p_binarywidth': '0'}

        # Now we set the arguments to pass to the parent class, which fills
        # in all the values to create an instantiatable IP block.

        # entity_name is the name of this particular manifestation of the ip
        # block. It might be the case that, for example, xbip_dsp48_macro
        # is used in a different VivadoIP block, in which case a different
        # entity_name should be used (otherwise the resultant HDL code will
        # have a name conflict).
        entity_name = 'DSP48E1'

        # Ports is the port mapping lookup described above.
        ports = port_mappings

        # ip_name is the name of the ip block to be created
        ip_name = 'xbip_dsp48_macro'

        # vendor, library and version are the config options to fully 
        # describe the ip block to Vivado
        vendor = 'xilinx.com'
        library = 'ip'
        version = '3.0'

        VivadoIP.__init__(
            self, entity_name, port_mappings, ip_name, vendor, library, 
            version, config)

# Since the VivadoIP block can be configurable, we need to create a 
# specific manifestation - passing arguments as necessary (which in this case
# is not applicable as VivadoDSPMacro has no arguments defined).
# 
# Note that this is not an instance of the IP block in the HDL sense, but 
# instead a fully described IP block from which instances can be created.
dsp_macro = VivadoDSPMacro()

@block
def DSP48E1(A, B, C, P, opmode, clock_enable, reset, clock):
    '''A MyHDL DSP48E1 block, using the encrypted IP when it is converted.
    '''

    # In this case, we've implemented something pretty close to how the 
    # DSP block actually works internally. This is not a requirement, and
    # the Python code does not need to be convertible.

    # Check the inputs
    check_intbv_signal(A, 'A', 25, signed=True)
    check_intbv_signal(B, 'B', 18, signed=True)
    check_intbv_signal(C, 'C', 48, signed=True)
    check_intbv_signal(P, 'P', 48, signed=True)
    check_intbv_signal(opmode, 'opmode', val_range=(0, N_DSP48E1_OPMODES))    
    check_bool_signal(clock_enable, 'clock_enable')    
    check_bool_signal(clock, 'clock')
    check_reset_signal(reset, 'reset', active=1, async=False)

    out_len = 48
    max_out = 2**(out_len - 1) - 1 # one bit for the sign
    min_out = -max_out

    A_register = Signal(intbv(val=0, min=A.min, max=A.max))
    B_register = Signal(intbv(val=0, min=B.min, max=B.max))

    M_register = Signal(intbv(val=0, min=min_out, max=max_out))
    C_register1 = Signal(intbv(val=0, min=min_out, max=max_out))
    C_register2 = Signal(intbv(val=0, min=min_out, max=max_out))
    
    P_register = Signal(intbv(val=0, min=min_out, max=max_out))

    # Set up the opmode registers.
    # Currently two input side registers.
    opmode_register1 = Signal(intbv(val=0, min=0, max=N_DSP48E1_OPMODES))
    opmode_register2 = Signal(intbv(val=0, min=0, max=N_DSP48E1_OPMODES))

    opmode_X = Signal(intbv(0)[2:])
    opmode_Y = Signal(intbv(0)[2:])
    opmode_Z = Signal(intbv(0)[3:])

    X_output = intbv(val=X_ZEROS, min=min_out, max=max_out)
    Y_output = intbv(val=Y_ZEROS, min=min_out, max=max_out)
    Z_output = intbv(val=Z_ZEROS, min=min_out, max=max_out)

    ALUMODE_ACCUMULATE = 0
    ALUMODE_DECCUMULATE = 3
    alumode = Signal(intbv(0)[4:])    

    @always_seq(clock.posedge, reset=reset)
    def opmode_pipeline():
        if clock_enable: # pragma: no branch
            opmode_register1.next = opmode
            opmode_register2.next = opmode_register1

    @always_comb
    def set_opmode_X():
        if opmode_register2 == DSP48E1_OPMODE_MULTIPLY:
            opmode_X.next = X_M
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_ADD:
            opmode_X.next = X_M
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_ACCUMULATE:
            opmode_X.next = X_M
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_DECCUMULATE:
            opmode_X.next = X_M
        else:
            if __debug__:
                raise ValueError('Unsupported Y opmode: %d', opmode_Y)
            pass

    @always_comb
    def set_opmode_Y():
        if opmode_register2 == DSP48E1_OPMODE_MULTIPLY:
            opmode_Y.next = Y_M
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_ADD:
            opmode_Y.next = Y_M
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_ACCUMULATE:
            opmode_Y.next = Y_M
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_DECCUMULATE:
            opmode_Y.next = Y_M
        else:
            if __debug__:
                raise ValueError('Unsupported Y opmode: %d', opmode_Y)
            pass

    @always_comb
    def set_opmode_Z():
        if opmode_register2 == DSP48E1_OPMODE_MULTIPLY:
            opmode_Z.next = Z_ZEROS
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_ADD:
            opmode_Z.next = Z_C
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_ACCUMULATE:
            opmode_Z.next = Z_P
        elif opmode_register2 == DSP48E1_OPMODE_MULTIPLY_DECCUMULATE:
            opmode_Z.next = Z_P
        else:
            if __debug__:
                raise ValueError('Unsupported Y opmode: %d', opmode_Y)
            pass

    @always_comb
    def set_ALUMODE():
        if opmode_register2 == DSP48E1_OPMODE_MULTIPLY_DECCUMULATE:
            alumode.next = ALUMODE_DECCUMULATE
        else:
            # default alumode
            alumode.next = ALUMODE_ACCUMULATE

    @always_comb
    def set_P():
        P.next = P_register

    @always_seq(clock.posedge, reset=reset)
    def dsp48e1_block():

        if clock_enable: # pragma: no branch
            # The partial products are combined in this implementation.
            # No problems with this as all we are doing is multiply/add or 
            # multiply/accumulate.
            if opmode_X == X_M:
                X_output[:] = M_register
            else:
                if __debug__:
                    raise ValueError('Unsupported X opmode: %d', opmode_X)
                pass

            if opmode_Y == Y_M:
                Y_output[:] = 0 # The full product is handled by X
            else:
                if __debug__:
                    raise ValueError('Unsupported Y opmode: %d', opmode_Y)
                pass

            if opmode_Z == Z_ZEROS:
                Z_output[:] = 0
            elif opmode_Z == Z_C:
                Z_output[:] = C_register2
            elif opmode_Z == Z_P:
                Z_output[:] = P_register
            else:
                if __debug__:
                    raise ValueError('Unsupported Z opmode: %d', opmode_Z)
                pass

            M_register.next = A_register * B_register

            A_register.next = A
            B_register.next = B

            C_register1.next = C
            C_register2.next = C_register1

            if alumode == ALUMODE_ACCUMULATE:
                P_register.next = Z_output + (X_output + Y_output)

            elif alumode == ALUMODE_DECCUMULATE:
                P_register.next = Z_output - (X_output + Y_output)

    A.read = True
    B.read = True
    C.read = True    
    P.driven = 'wire'
    opmode.read = True
    clock_enable.read = True
    clock.read = True
    reset.read = True

    # The instance is created here. 
    # get_verilog_instance and get_vhdl_instance return an instance of 
    # a child class of string. This means it can be assigned directly to
    # the MyHDL expected verilog_code and vhdl_code, fitting trivially
    # into MyHDL's conversion tools.
    # The fact that a child class is used means the details of the IP
    # can be looked up from the v*_code attribute, wherever it is in the
    # hierarchy. This is how the cosimulation facility works.
    DSP48E1.verilog_code = dsp_macro.get_verilog_instance()
    DSP48E1.vhdl_code = dsp_macro.get_vhdl_instance()

    return (dsp48e1_block, opmode_pipeline, 
            set_opmode_X, set_opmode_Y, set_opmode_Z, set_P, set_ALUMODE)

