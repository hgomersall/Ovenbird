
from myhdl import *
from enum import Enum

import string

import os

import inspect

__all__ = ['VivadoIP', 'PortDirection']

_vhdl_wrapper_template = string.Template('''
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity ${entity_name} is
    port (
            ${entity_ports}
         );
end entity ${entity_name};


architecture MyHDL of ${entity_name} is

    component ${module_name}
        port (
                ${ip_component_ports}
             );
    end component ${module_name};

    ${wrapped_signal_instantiations};

begin

    ${wrapped_signal_assignments};

    ip_instance : ${module_name}
    port map (
                ${ip_port_mappings}
             );

end architecture MyHDL;
''')

_vhdl_instantiation_template = string.Template('''
${instance_name}: entity work.${entity_name}(MyHDL)
port map (
    ${port_mappings}
);
''')

_verilog_wrapper_template = string.Template('''
module entity_name (
    ${entity_ports}
);
${module_name} ip_instance (
    ${ip_port_mappings}
);

endmodule
''')

_verilog_instantiation_template = string.Template('''
${module_name} ${instance_name} (
    ${port_mappings}
);
''')

class PortDirection(Enum):
    input = 1
    output = 2

class VivadoIP(object):

    def __init__(self, entity_name, ports, ip_name, vendor, library, version,
                 config):
        '''
        Presents a piece of Vivado IP in a form that can be used to generate
        suitable HDL code, including generating a wrapper to perform the
        instantiation.

        ``entity_name`` is the name of the entity that can be instantiated
        in the main hdl.

        ``ports`` is a dictionary of ports. The keys are the port names and
        the values are tuples of ``(type, direction, ip_mapping)``.
        ``type`` should be an object akin to a myhdl type that returns a bit
        length with ``len()`` and where relevant has a min and max property.
        ``ip_mapping`` is the name of the corresponding port in the ip block.
        This is of prime importance in the construction of the HDL IP wrapper.
        Essentially when the wrapper is a new Verilog or VHDL block with
        an interface given by the keys of the ``ports`` dictionary. It is
        possible to use different port names from the calling MyHDL when
        the ``V*_instance`` is created (see the respective function for
        more information).

        ``ip_name`` is the name of the ip block that is created and wrapped.

        ``vendor`` is the name of the vendor supplying the ip block as
        used to define the location of the ip block - e.g. 'xilinx.com'.

        ``library`` is a string of the ip library name.

        ``version`` a string containing the ip version number e.g. '3.0'.

        ``config`` is a dictionary that that defines the config options to set
        on the entity at instantiation. They are not checked for validity at
        any point, so they should correspond to a valid IP config options. The
        full set of IP properties (which is a superset of the config options)
        can be queried with tcl in Vivado with ``list_property`` (to simply
        list) or ``report_property`` (for more detail). The config options are
        those prefixed with ``CONFIG.`` (which is not needed in the config
        arguments). The config values should all be strings.
        '''

        self.entity_name = entity_name
        self.ip_name = ip_name
        self.module_name = ip_name + '_' + entity_name
        self.ports = ports

        self.vendor = vendor
        self.library = library
        self.version = version

        self.config = config

        self._vhdl_instance_idx = 0
        self._verilog_instance_idx = 0

    @property
    def tcl_string(self):
        '''The tcl string that will instantiate the IP and set any config
        options and output products.

        The name of the created object is set by concatenating
        the original entity name to the ip_name separated by an underscore.
        That is: ``entity_name + '_' + ip_name``.
        '''
        tcl_creation_string = (
            'create_ip -name %s -vendor %s -library %s '
            '-version %s -module_name %s\n' % (
                self.ip_name, self.vendor, self.library, self.version,
                self.module_name))

        config_string = ' '.join(
            'CONFIG.%s {%s}' % (option, value) for
            option, value in self.config.items())

        tcl_config_string = (
            'set_property -dict [list %s] [get_ips %s]\n' %
            (config_string, self.module_name))

        tcl_output_products_string = (
            'generate_target all [get_ips %s]\n' % (self.module_name,))

        tcl_complete_string = (
            tcl_creation_string + tcl_config_string +
            tcl_output_products_string)

        return tcl_complete_string

    def get_vhdl_instance(self, **port_mappings):
        '''Create and return a ``HDLCodeWithIP`` object for instantiating
        a unique instance in VHDL. The ``HDLCodeWthIP`` block looks and acts
        like a string, but has access to the class instance that generated
        it (i.e. this object).

        The string returned is designed to be a suitable ``vhdl_code``
        string that instantiates an instance of the IP wrapper HDL block in
        converted code. The actual IP wrapper needs to be created separately
        with a call to ``write_vhdl_wrapper``.

        ``port_mappings`` is an optional set of keyword arguments that maps
        port names of the IP wrapper to MyHDL signals. For example, if there
        is a port mapping ``output_port=myhdl_output_signal``, this will
        create the mapping in the returned string as
        ``'output_port=>${myhdl_output_signal}'``. Each key in
        ``port_mappings`` should correspond to a port defined in ``ports``
        during initial instantiation, otherwise a ``ValueError`` will be
        raised. Note that ``${myhdl_output_signal}`` is actually a template
        string that is replaced at conversion time.

        Each signal passed in through ``port_mappings`` has its ``driven``
        or ``read`` parameter set appropriately, meaning this is unncessary
        on the user side.

        ``port_mappings`` is optional; if ports are missing then the MyHDL
        name is set to be the same as what was set by ``ports`` during the
        initial instantiation of this object (i.e. if a hypothetical port
        ``A`` was not set by ``port_mappings``, the return string would
        contain ``'A=>${A}'``).

        In addition to the advantage of name changing and specifying
        read/driven automatically, explicitly setting ``port_mappings``
        also allows for the port to be checked for type and length
        consisistency, avoiding potential problems being pushed to the VHDL
        tool.

        The name of the created instance is given by
        ``entity_name + '_' + str(N)``, where ``entity_name`` is the name
        set during instantiation of this object and ``N`` is a unique number
        giving the instance number. Each call to this method will generate a
        new instance (with ``N`` beginning at 0 and increasing).
        '''

        instance_name = self.entity_name + '_' + str(self._vhdl_instance_idx)
        self._vhdl_instance_idx += 1

        port_mapping_strings = []
        for port_name in self.ports:

            if port_name in port_mappings:
                instance_port_name = port_mappings[port_name]
            else:
                instance_port_name = port_name

            instance_port_string = (
                '${' + instance_port_name.replace('.', '_') + '}')

            port_mapping_strings.append(
                '%s=>%s' % (
                    port_name.replace('.', '_'), instance_port_string))

        all_port_mappings = ',\n    '.join(port_mapping_strings)

        vhdl_instantiation_string = _vhdl_instantiation_template.substitute(
            instance_name=instance_name,
            entity_name=self.entity_name,
            port_mappings=all_port_mappings)

        return HDLCodeWithIP(vhdl_instantiation_string, self)

    def write_vhdl_wrapper(self, output_directory):
        '''Generates the vhdl file that wraps the IP block, wrapping the
        ports to convert between the myhdl types and names and the Vivado
        expected types and names.

        The file is written to ``output_directory``.

        Returns the filename that is written.
        '''

        if not os.path.isdir(output_directory):
            raise IOError('%s is not a directory.' % (output_directory,))

        entity_port_strings = []
        wrapped_signal_instantiation_strings = []
        wrapped_signal_assignment_strings = []
        ip_component_port_strings = []
        ip_port_mapping_strings = []

        for port_name in self.ports:
            port_type = self.ports[port_name][0]
            port_direction = self.ports[port_name][1]
            ip_port_mapping = self.ports[port_name][2]

            port_length = len(port_type)
            if port_length > 1:
                ip_type_string = 'std_logic_vector'

                if port_type.min < 0:
                    entity_type_string = 'signed'
                else:
                    entity_type_string = 'unsigned'

                size_string = "(%d downto 0)" % (port_length - 1)
            else:
                port_is_signed = False
                entity_type_string = 'std_logic'
                ip_type_string = 'std_logic'
                size_string = ''

            if port_direction == PortDirection.input:
                direction_string = 'in'

                wrapped_signal_assignment_strings.append(
                    'wrapped_%s <= %s(%s)' %
                    (port_name, ip_type_string, port_name))

            elif port_direction == PortDirection.output:
                direction_string = "out"

                wrapped_signal_assignment_strings.append(
                    '%s <= %s(wrapped_%s)' %
                    (port_name, entity_type_string, port_name))
            else:
                raise ValueError('Unsupported direction')

            entity_port_strings.append(
                '%s: %s %s%s' % (port_name, direction_string,
                                 entity_type_string, size_string))

            wrapped_signal_instantiation_strings.append(
                'signal wrapped_%s: %s%s' % (
                    port_name, ip_type_string, size_string))

            ip_component_port_strings.append(
                '%s: %s %s%s' % (ip_port_mapping, direction_string,
                                 ip_type_string, size_string))

            ip_port_mapping_strings.append(
                '%s => wrapped_%s' % (ip_port_mapping, port_name))


        entity_ports = (';\n' + ' ' * 12).join(entity_port_strings)
        ip_component_ports = (
            ';\n' + ' ' * 16).join(ip_component_port_strings)
        wrapped_signal_instantiations = (
            ';\n' + ' ' * 4).join(wrapped_signal_instantiation_strings)

        wrapped_signal_assigments = (
            ';\n' + ' ' * 4).join(wrapped_signal_assignment_strings)

        ip_port_mappings = (',\n' + ' ' * 16).join(ip_port_mapping_strings)

        vhdl_wrapper_string = _vhdl_wrapper_template.substitute(
            entity_ports=entity_ports,
            ip_component_ports=ip_component_ports,
            wrapped_signal_instantiations=wrapped_signal_instantiations,
            wrapped_signal_assignments=wrapped_signal_assigments,
            ip_port_mappings=ip_port_mappings,
            module_name=self.module_name,
            entity_name=self.entity_name)

        wrapper_filename = os.path.join(
            output_directory, self.entity_name + '.vhd')

        if os.path.exists(wrapper_filename):
            raise IOError('File %s already exists - '
                          'refusing to overwrite it.')

        with open(wrapper_filename, 'w') as f:
            f.write(vhdl_wrapper_string)

        return wrapper_filename

    def get_verilog_instance(self, **port_mappings):
        '''Create and return a ``HDLCodeWithIP`` object for instantiating
        a unique instance in Verilog. The ``HDLCodeWthIP`` block looks and acts
        like a string, but has access to the class instance that generated
        it (i.e. this object).

        The string returned is designed to be a suitable ``verilog_code``
        string that instantiates an instance of the IP wrapper HDL block in
        converted code. Unlike VHDL, it is unncessary to write a Verilog
        wrapper.

        ``port_mappings`` is an optional set of keyword arguments that maps
        port names of the IP wrapper to MyHDL signals. For example, if there
        is a port mapping ``output_port=myhdl_output_signal``, this will
        create the mapping in the returned string as
        ``'.output_port(${myhdl_output_signal})'``. Each key in
        ``port_mappings`` should correspond to a port defined in ``ports``
        during initial instantiation, otherwise a ``ValueError`` will be
        raised. Note that ``${myhdl_output_signal}`` is actually a template
        string that is replaced at conversion time.

        Each signal passed in through ``port_mappings`` has its ``driven``
        or ``read`` parameter set appropriately, meaning this is unncessary
        on the user side.

        ``port_mappings`` is optional; if ports are missing then the MyHDL
        name is set to be the same as what was set by ``ports`` during the
        initial instantiation of this object (i.e. if a hypothetical port
        ``A`` was not set by ``port_mappings``, the return string would
        contain ``'.A(${A})'``).

        In addition to the advantage of name changing and specifying
        read/driven automatically, explicitly setting ``port_mappings``
        also allows for the port to be checked for type and length
        consisistency, avoiding potential problems being pushed to the VHDL
        tool.

        The name of the created instance is given by
        ``entity_name + '_' + str(N)``, where ``entity_name`` is the name
        set during instantiation of this object and ``N`` is a unique number
        giving the instance number. Each call to this method will generate a
        new instance (with ``N`` beginning at 0 and increasing).
        '''
        '''Create and return a ``HDLCodeWithIP`` object for instantiating
        a unique instance in Verilog. The ``HDLCodeWthIP`` block looks and acts
        like a string, but has access to the class instance that generated
        (i.e. this object).

        The name of the created instance is given by
        ``self.entity_name + '_' + str(N)``,
        where ``N`` is a unique number giving the instance number. Each call
        to this method will generate a new instance (with ``N`` beginning
        at 0 and increasing).

        The port mappings are set to be a mapping from each port name on
        this object to a template variable of the same name.

        So, for example, if there is a port named `'A'`, then the mapping
        `'.A(${A})'` will be created. MyHDL will then replace `$A` with a
        suitable Verilog signal when the top level VHDL file is created.

        This requires that the MyHDL names are the same as the names set
        in this IP block.
        '''
        instance_name = self.entity_name + '_' + str(
            self._verilog_instance_idx)

        self._verilog_instance_idx += 1

        port_mapping_strings = []
        for port_name in self.ports:
            if port_name in port_mappings:
                instance_port_name = port_mappings[port_name]
            else:
                instance_port_name = port_name

            ip_port_mapping = self.ports[port_name][2]
            instance_port_string = '${' + instance_port_name + '}'

            port_mapping_strings.append(
                '.%s(%s)' % (ip_port_mapping, instance_port_string))

        all_port_mappings = ',\n    '.join(port_mapping_strings)

        verilog_instantiation_string = (
            _verilog_instantiation_template.substitute(
                instance_name=instance_name,
                module_name=self.module_name,
                port_mappings=all_port_mappings))

        return HDLCodeWithIP(verilog_instantiation_string, self)


class HDLCodeWithIP(str):

    def __new__(cls, hdl_code, ip_instance):

        if not isinstance(ip_instance, VivadoIP):
            raise ValueError('ip_instance should be an instance of VivadoIP')

        new_obj = str.__new__(cls, hdl_code)
        new_obj.ip_instance = ip_instance
        return new_obj

    def __init__(self, hdl_code, ip_instance):
        '''Creates a code block from an IP block that can be
        assigned to the `.vhdl_code` or `.verilog_code` attributes of a
        myhdl block.

        This means the ip_instance attribute can be later extracted
        from the block.'
        '''
        pass


