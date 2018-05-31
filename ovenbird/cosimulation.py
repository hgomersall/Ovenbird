
from veriutils import SynchronousTest
from veriutils.cosimulation import PERIOD

import ovenbird

from myhdl import *
import myhdl
from myhdl.conversion._toVHDL import _shortversion
myhdl_vhdl_package_filename = "pck_myhdl_%s.vhd" % _shortversion

import tempfile
import os
import string
import shutil
import subprocess
import csv
import copy
import re
import collections
import warnings

try: # pragma: no branch
    # Python 2
    from ConfigParser import RawConfigParser
except ImportError:
    # Python 3
    from configparser import RawConfigParser

__all__ = ['vivado_vhdl_cosimulation', 'vivado_verilog_cosimulation',
           'VivadoError']

_simulate_tcl_template = string.Template('''
config_webtalk -user off
create_project $project_name $project_path -part $part

set_property target_language $target_language [current_project]
set_param project.enableVHDL2008 1
set_property enable_vhdl_2008 1 [current_project]

$load_and_configure_ips
add_files -norecurse {$vhdl_files $verilog_files $ip_additional_hdl_files}
if {[string length [get_files {$vhdl_files}]] != 0} {
    set_property FILE_TYPE {VHDL 2008} [get_files {$vhdl_files}]
}

update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
set_property -name {xsim.simulate.runtime} -value {${time}ns} -objects [current_fileset -simset]
launch_simulation
$vcd_capture_script
close_sim
close_project
''')

_vcd_capture_template = string.Template('''
restart
open_vcd ${vcd_filename}
log_vcd
run ${time}ns
close_vcd
''')

def _populate_vivado_ip_list(block, hdl):

    try:
        if hdl == 'VHDL':
            vivado_ip_list = [block.vhdl_code.code.ip_instance]
        else:
            vivado_ip_list = [block.verilog_code.code.ip_instance]

    except AttributeError:
        vivado_ip_list = []

    for sub in block.subs:
        if isinstance(sub, myhdl._block._Block):
            vivado_ip_list += _populate_vivado_ip_list(sub, hdl)

    return vivado_ip_list

def _get_signal_names_to_port_names(filename, comment_string):

    with open(filename) as f:
        code = f.read()

    signal_name_mappings = {}
    for each in re.finditer(
        '^%s <name_annotation>.*?$' % comment_string, code, re.MULTILINE):
        vals = code[each.start():each.end()].split()

        signal_name_mappings[vals[2]] = vals[3]

    return signal_name_mappings


class VivadoError(RuntimeError):
    pass

def _vivado_generic_cosimulation(
    target_language, cycles, dut_factory, ref_factory, args,
    arg_types, period, custom_sources, keep_temp_files, config_file,
    template_path_prefix, vcd_name):

    if ovenbird.VIVADO_EXECUTABLE is None:
        raise EnvironmentError('Vivado executable not in path')

    config = RawConfigParser()
    config.read(config_file)

    sim_object = SynchronousTest(dut_factory, ref_factory, args, arg_types,
                                 period, custom_sources)
    # We need to create the test data
    myhdl_outputs = sim_object.cosimulate(cycles, vcd_name=vcd_name)

    # StopSimulation might be been called, so we should handle that.
    # Use the ref outputs, as that can't be None
    # outputs_length is the number of cycles we use for the vivado
    # cosimulation
    outputs_length = None
    for each_signal in myhdl_outputs[1]:
        # axi_stream args should be split up before checking
        if arg_types[each_signal] == 'axi_stream_out':
            signal_output = myhdl_outputs[1][each_signal]['signals']
        else:
            signal_output = myhdl_outputs[1][each_signal]

        _length = len(signal_output)

        if outputs_length is not None:
            assert outputs_length == _length

        outputs_length = _length

    # One cycle is lost in the vivado simulation for the propagation
    # delay between reading and writing.
    _cycles = outputs_length + 1

    tmp_dir = tempfile.mkdtemp()

    try:
        project_name = 'tmp_project'
        project_path = os.path.join(tmp_dir, project_name)

#     FIXME - this should be uncommented. There is a bug in myhdl in which
#     multiple converts cause problems.
#        # Firstly check the dut is convertible
#        # We wrap the actual dut in an argumentless block so the
#        # issue of non-convertible top level signals goes away
#        @block
#        def minimal_wrapper():
#            return dut_factory(**args)
#
#        with warnings.catch_warnings():
#            # We don't worry about warnings at this stage - they are to be
#            # expected. We only really care about errors.
#            warnings.simplefilter("ignore")
#            minimal_wrapper().convert(hdl=target_language, path=tmp_dir)

        time = period * _cycles

        try:
            ip_dependencies = dut_factory.ip_dependencies
        except AttributeError:
            ip_dependencies = ()

        vhdl_files = []
        verilog_files = []
        ip_additional_hdl_files = []

        load_and_configure_ips_tcl_string = ''

        if vcd_name is not None:
            vcd_filename = os.path.realpath(vcd_name + '.vivado.vcd')
            vcd_capture_script = _vcd_capture_template.safe_substitute(
                {'vcd_filename': vcd_filename,
                 'time': time})

        else:
            vcd_capture_script = ''

        if target_language == 'VHDL':
            try:
                vhdl_dependencies = list(dut_factory.vhdl_dependencies)
            except AttributeError:
                vhdl_dependencies = []

            convertible_top_filename = os.path.join(
                tmp_dir, 'dut_convertible_top.vhd')

            vhdl_dut_files = [
                convertible_top_filename,
                os.path.join(tmp_dir, myhdl_vhdl_package_filename)]

            vhdl_files += vhdl_dependencies + vhdl_dut_files

            # Generate the output VHDL files
            signal_output_filename = os.path.join(tmp_dir, 'signal_outputs')
            convertible_top = sim_object.dut_convertible_top(
                tmp_dir, signal_output_filename='signal_outputs',
                axi_stream_packets_filename_prefix='axi_stream_out')

            ip_list = set(_populate_vivado_ip_list(convertible_top, 'VHDL'))

            for ip_object in ip_list:

                ip_additional_hdl_files.append(
                    ip_object.write_vhdl_wrapper(tmp_dir))

                load_and_configure_ips_tcl_string += ip_object.tcl_string

            toVHDL.initial_values = True

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always', myhdl.ToVHDLWarning)
                try:
                    convertible_top.convert(hdl='VHDL', path=tmp_dir)

                except myhdl.ConversionError as e:
                    raise ovenbird.OvenbirdConversionError(
                        'The convertible top from Veriutils failed to convert '
                        'with the following error:\n%s\n'
                        'Though this could be a problem with your code, it '
                        'could also mean there is a problem with the '
                        'way you set Veriutils up. Are all the signals defined '
                        'correctly and the signal types set up correctly '
                        '(importantly, all the outputs are defined as such)? '
                        'Alternatively it could be a bug in Veriutils.' % str(e))
                    # FIXME currently the conversion test to verify user code
                    # is broken due to a myhdl bug (see above). The below
                    # exception string should be enabled when the bug is fixed.
                    #raise ovenbird.OvenbirdConversionError(
                    #    'The convertible top from Veriutils failed to convert '
                    #    'with the following error: %s\n'
                    #    'The code that has been passed in for verification (i.e. '
                    #    'that you wrote) has been verified as converting '
                    #    'properly. This means there could be a problem with the '
                    #    'way you set Veriutils up. Are all the signals defined '
                    #    'correctly and the signal types set up correctly '
                    #    '(importantly, all the outputs are defined as such)? '
                    #    'Alternatively it could be a bug in Veriutils.')

                vhdl_conversion_warnings = w

            signal_name_mappings = _get_signal_names_to_port_names(
                convertible_top_filename, '--')

            for warning in vhdl_conversion_warnings:
                message = str(warning.message)

                for internal_name in signal_name_mappings:
                    if internal_name in message:
                        port_name = signal_name_mappings[internal_name]
                        message = str.replace(
                            message, internal_name,
                            '%s (internally to VHDL: %s)' %
                            (port_name, internal_name))

                warnings.warn_explicit(
                    message, warning.category, warning.filename,
                    warning.lineno)

        elif target_language == 'Verilog':
            try:
                verilog_dependencies = list(dut_factory.verilog_dependencies)
            except AttributeError:
                verilog_dependencies = []

            convertible_top_filename = os.path.join(
                tmp_dir, 'dut_convertible_top.v')
            verilog_dut_files = [convertible_top_filename,]

            verilog_files += verilog_dependencies + verilog_dut_files

            # Generate the output Verilog files
            signal_output_filename = os.path.join(tmp_dir, 'signal_outputs')
            convertible_top = sim_object.dut_convertible_top(
                tmp_dir, signal_output_filename='signal_outputs',
                axi_stream_packets_filename_prefix='axi_stream_out')

            ip_list = set(_populate_vivado_ip_list(convertible_top, 'Verilog'))

            for ip_object in ip_list:
                load_and_configure_ips_tcl_string += ip_object.tcl_string

            toVerilog.initial_values = True

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always', myhdl.ToVerilogWarning)
                try:
                    convertible_top.convert(hdl='Verilog', path=tmp_dir)
                except myhdl.ConversionError as e:

                    raise ovenbird.OvenbirdConversionError(
                        'The convertible top from Veriutils failed to convert '
                        'with the following error: %s\n'
                        'The code that has been passed in for verification (i.e. '
                        'that you wrote) has been verified as converting '
                        'properly. This means there could be a problem with the '
                        'way you set Veriutils up. Are all the signals defined '
                        'correctly and the signal types set up correctly '
                        '(importantly, all the outputs are defined as such)? '
                        'Alternatively it could be a bug in Veriutils.' % str(e))

                verilog_conversion_warnings = w

            signal_name_mappings = _get_signal_names_to_port_names(
                convertible_top_filename, '//')

            for warning in verilog_conversion_warnings:
                message = str(warning.message)

                for internal_name in signal_name_mappings:
                    if internal_name in message:
                        port_name = signal_name_mappings[internal_name]
                        message = str.replace(
                            message, internal_name,
                            '%s (internally to Verilog: %s)' %
                            (port_name, internal_name))

                warnings.warn_explicit(
                    message, warning.category, warning.filename,
                    warning.lineno)

        else:
            raise ValueError('Target language must be \'Verilog\' or '
                             '\'VHDL\'')

        for each_hdl_file in (vhdl_files + verilog_files +
                              ip_additional_hdl_files):
            # The files should all now exist
            if not os.path.exists(each_hdl_file):
                raise EnvironmentError(
                    'An expected HDL file is missing: %s'
                    % (each_hdl_file))

        vhdl_files_string = ' '.join(vhdl_files)
        verilog_files_string = ' '.join(verilog_files)
        ip_additional_hdl_files_string = ' '.join(ip_additional_hdl_files)

        template_substitutions = {
            'target_language': target_language,
            'part': config.get('General', 'part'),
            'project_name': project_name,
            'project_path': project_path,
            'time': time,
            'load_and_configure_ips': load_and_configure_ips_tcl_string,
            'vhdl_files': vhdl_files_string,
            'verilog_files': verilog_files_string,
            'ip_additional_hdl_files': ip_additional_hdl_files_string,
            'vcd_capture_script': vcd_capture_script}

        simulate_script = _simulate_tcl_template.safe_substitute(
            template_substitutions)

        simulate_script_filename = os.path.join(
            tmp_dir, 'simulate_script.tcl')

        with open(simulate_script_filename, 'w') as simulate_script_file:
            simulate_script_file.write(simulate_script)

        vivado_process = subprocess.Popen(
            [ovenbird.VIVADO_EXECUTABLE, '-nolog', '-nojournal', '-mode',
             'batch', '-source', simulate_script_filename],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        out, err = vivado_process.communicate()

        if err != b'':
            if target_language == 'VHDL':
                xvhdl_log_filename = os.path.join(
                    tmp_dir, 'tmp_project', 'tmp_project.sim', 'sim_1',
                    'behav', 'xvhdl.log')

                if xvhdl_log_filename.encode() in err:
                    with open(xvhdl_log_filename, 'r') as log_file:
                        err += '\n'
                        err += 'xvhdl.log:\n'
                        err += log_file.read()

                raise VivadoError(
                    'Error running the Vivado VHDL simulator:\n%s' % err)

            elif target_language == 'Verilog':
                xvhdl_log_filename = os.path.join(
                    tmp_dir, 'tmp_project', 'tmp_project.sim', 'sim_1',
                    'behav', 'xvlog.log')

                if xvhdl_log_filename.encode() in err:
                    with open(xvhdl_log_filename, 'r') as log_file:
                        err += '\n'
                        err += 'xvlog.log:\n'
                        err += log_file.read()

                raise VivadoError(
                    'Error running the Vivado Verilog simulator:\n%s' % err)

        with open(signal_output_filename, 'r') as signal_output_file:
            signal_reader = csv.DictReader(signal_output_file, delimiter=',')

            vivado_signals = [row for row in signal_reader]

        # Most of the dut outputs will be the same as ref, we then overwrite
        # the others from the written file.
        dut_outputs = copy.copy(sim_object.outputs[1])
        ref_outputs = sim_object.outputs[1]

        vivado_signal_keys = vivado_signals[0].keys()

        # Rearrange the output signals into the correct form
        _vivado_signals = {key: [] for key in vivado_signals[0].keys()}

        for each_row in vivado_signals:
            for each_key in vivado_signal_keys:
                _vivado_signals[each_key].append(each_row[each_key])

        vivado_signals = _vivado_signals

        interface_outputs = {}
        siglist_outputs = {}
        for each_signal_name_str in vivado_signals:

            each_dut_outputs = []

            sig_container, signal_type, each_signal = (
                each_signal_name_str.split(' '))

            for dut_str_value in vivado_signals[each_signal_name_str]:
                try:
                    if signal_type == 'bool':
                        each_value = bool(int(dut_str_value))
                    else:
                        # We assume an intbv
                        _each_value = (
                            intbv(dut_str_value)[len(dut_str_value):])

                        if signal_type =='signed':
                            each_value = _each_value.signed()
                        else:
                            each_value = _each_value

                except ValueError:
                    # Probably an undefined.
                    each_value = None

                each_dut_outputs.append(each_value)

            # add each per-signal list into a data structure that
            # can be easily turned into the correct output when it is not
            # possible to add it directly.
            if sig_container == 'interface':
                output_name_list = each_signal.split('.')

                # We have an interface, so group the recorded signals
                # of the interface together.

                # FIXME Only one level of interface supported
                interface_outputs.setdefault(
                    output_name_list[0], {})[output_name_list[1]] = (
                        each_dut_outputs)

            elif sig_container == 'list':
                # We have a list
                parsed_header = re.search(
                    '(?P<list_name>.*)\[(?P<index>.*)\]', each_signal)

                siglist_name = parsed_header.group('list_name')
                siglist_index = int(parsed_header.group('index'))

                siglist_outputs.setdefault(
                    siglist_name, {})[siglist_index] = each_dut_outputs

            else:
                # We have a normal signal
                dut_outputs[each_signal] = each_dut_outputs

        # Now convert the data structures into suitable outputs.

        for each_siglist in siglist_outputs:

            # Order the values by the siglist_index
            ordered_siglist_output = collections.OrderedDict(sorted(
                siglist_outputs[each_siglist].items(), key=lambda t: t[0]))

            new_dut_output = []

            for each_list_out in zip(*ordered_siglist_output.values()):
                new_dut_output.append(list(each_list_out))

            dut_outputs[each_siglist] = new_dut_output

        for each_interface in interface_outputs:

            signal_type = arg_types[each_interface]

            attr_names = interface_outputs[each_interface].keys()

            reordered_interface_outputs =  zip(
                *(interface_outputs[each_interface][key] for
                  key in attr_names))

            # We need to write the interface values to dut_outputs, but
            # taking the values from ref_outputs if the interface signal was
            # not an output.
            new_dut_output = []

            if signal_type == 'axi_stream_out':
                for ref_output, simulated_output in zip(
                    dut_outputs[each_interface]['signals'],
                    reordered_interface_outputs):

                    new_interface_out = ref_output.copy()
                    new_interface_out.update(
                        dict(zip(attr_names, simulated_output)))

                    new_dut_output.append(new_interface_out)

                    dut_outputs[each_interface] = {'signals': new_dut_output}
            else:
                for ref_output, simulated_output in zip(
                    dut_outputs[each_interface], reordered_interface_outputs):

                    new_interface_out = ref_output.copy()
                    new_interface_out.update(
                        dict(zip(attr_names, simulated_output)))

                    new_dut_output.append(new_interface_out)

                    dut_outputs[each_interface] = new_dut_output

        # Now extract the axi signals
        for each_signal in ref_outputs:

            packets = []
            if arg_types[each_signal] == 'axi_stream_out':
                axi_out_filename = os.path.join(
                    tmp_dir, 'axi_stream_out' + '_' + each_signal)

                with open(axi_out_filename, 'r') as axi_out_file:
                    axi_packet_reader = csv.DictReader(
                        axi_out_file, delimiter=',')
                    vivado_axi_packet = [row for row in axi_packet_reader]

                packet = []
                for transaction in vivado_axi_packet:
                    packet.append(int(transaction['TDATA'], 2))
                    try:
                        if int(transaction['TLAST']):
                            packets.append(packet)
                            packet = []
                    except KeyError:
                        pass

                dut_outputs[each_signal]['packets'] = packets
                dut_outputs[each_signal]['incomplete_packet'] = packet

        for each_signal in ref_outputs:
            # Now only output the correct number of cycles

            if arg_types[each_signal] == 'axi_stream_out':
                ref_outputs[each_signal]['signals'] = (
                    ref_outputs[each_signal]['signals'][:outputs_length])
                dut_outputs[each_signal]['signals'] = (
                    dut_outputs[each_signal]['signals'][:outputs_length])
            else:
                ref_outputs[each_signal] = (
                    ref_outputs[each_signal][:outputs_length])
                dut_outputs[each_signal] = (
                    dut_outputs[each_signal][:outputs_length])

    finally:

        if not keep_temp_files:
            shutil.rmtree(tmp_dir)
        else:
            print('As requested, the temporary files have not been deleted.'
                  '\nThey can be found in %s.' % (tmp_dir,))

    return dut_outputs, ref_outputs


def vivado_vhdl_cosimulation(
    cycles, dut_factory, ref_factory, args, arg_types,
    period=PERIOD, custom_sources=None, keep_temp_files=False,
    config_file='veriutils.cfg', template_path_prefix='', vcd_name=None):
    '''Run a cosimulation in which the device under test is simulated inside
    Vivado, using VHDL as the intermediate language.

    This function has exactly the same interface as myhdl_cosimulation.

    The outputs should be identical to from myhdl_cosimulation except for
    one important caveat: until values are initialised explicitly, they
    are recorded as undefined. Undefined values are set to None in the output.

    This is particularly noticeable in the case when an asynchronous reset
    is used. Care should be taken to handle the outputs appropriately.

    By default, all the temporary files are cleaned up after use. This
    behaviour can be turned off by settings ``keep_temp_files`` to ``True``.
    '''

    target_language = 'VHDL'

    dut_outputs, ref_outputs = _vivado_generic_cosimulation(
        target_language, cycles, dut_factory, ref_factory, args,
        arg_types, period, custom_sources, keep_temp_files,
        config_file, template_path_prefix, vcd_name)

    return dut_outputs, ref_outputs

def vivado_verilog_cosimulation(
    cycles, dut_factory, ref_factory, args, arg_types,
    period=PERIOD, custom_sources=None, keep_temp_files=False,
    config_file='veriutils.cfg', template_path_prefix='', vcd_name=None):
    '''Run a cosimulation in which the device under test is simulated inside
    Vivado, using Verilog as the intermediate language.

    This function has exactly the same interface as myhdl_cosimulation.

    The outputs should be identical to from myhdl_cosimulation except for
    one important caveat: until values are initialised explicitly, they
    are recorded as undefined. Undefined values are set to None in the output.

    This is particularly noticeable in the case when an asynchronous reset
    is used. Care should be taken to handle the outputs appropriately.

    By default, all the temporary files are cleaned up after use. This
    behaviour can be turned off by settings ``keep_temp_files`` to ``True``.
    '''

    target_language = 'Verilog'

    dut_outputs, ref_outputs = _vivado_generic_cosimulation(
        target_language, cycles, dut_factory, ref_factory, args,
        arg_types, period, custom_sources, keep_temp_files,
        config_file, template_path_prefix, vcd_name)

    return dut_outputs, ref_outputs

