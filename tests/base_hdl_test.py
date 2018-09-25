
import unittest
from random import randrange
from myhdl import Signal, intbv

from mock import patch, call

def get_signed_intbv_rand_signal(width, val_range=None, init_value=0):
    '''Create a signed intbv random signal.
    '''
    if val_range is not None:
        min_val = val_range[0]
        max_val = val_range[1]
    else:
        min_val = -(2**(width - 1) - 1)
        max_val = 2**(width - 1)

    signal = Signal(intbv(init_value, min=min_val, max=max_val))
    signal.val[:] = randrange(min_val, max_val)

    return signal, min_val, max_val


def get_unsigned_intbv_rand_signal(width, init_value=0):
    '''Create an unsigned intbv random signal.
    '''
    min_val = 0
    max_val = 2**(width)
    signal = Signal(intbv(val=init_value, min=min_val, max=max_val))
    signal.val[:] = randrange(min_val, max_val)

    return signal, min_val, max_val


class TestCase(unittest.TestCase):
    '''Implements a python version agnostic version of unittest.TestCase.
    '''
    def __init__(self, *args, **kwargs):

        super(TestCase, self).__init__(*args, **kwargs)

        if not hasattr(self, 'assertRaisesRegex'): # pragma: no branch
            self.assertRaisesRegex = self.assertRaisesRegexp


class HDLTestCase(TestCase):
    '''Add some useful HDL specific methods.
    '''
    def setUp(self):
        self.default_args = {}

    def do_port_check_intbv_test(self, constructor, port_name, width=None,
                                 signed=False, val_range=None,
                                 attribute=None):
        '''Checks the intbv port test was performed on the specified port
        with the given port name and width. If attribute is not None,
        then the specified attribute on the given port name is used (e.g.
        for interfaces).
        '''
        if attribute is None:
            port_to_check = self.default_args[port_name]
        else:
            port_to_check = getattr(self.default_args[port_name], attribute)
            port_name += '.%s' % (attribute,)

        patch_location = constructor.__module__ + '.check_intbv_signal'
        with patch(patch_location) as (mock_check_function):

            # Make the call
            constructor(**self.default_args)

            mock_check_function.call_args_list

            # Enforce a certain calling convention that guarantees everything
            # is nice and consistent.
            if width is not None:
                self.assertIn(
                    call(port_to_check, port_name, width, signed=signed),
                    mock_check_function.call_args_list)
            else:
                self.assertIn(
                    call(port_to_check, port_name, val_range=val_range),
                    mock_check_function.call_args_list)


    def do_port_check_bool_test(self, constructor, port_name):
        '''Checks the bool port test was performed on the specified port
        with the given port name.
        '''
        port_to_check = self.default_args[port_name]

        patch_location = constructor.__module__ + '.check_bool_signal'
        with patch(patch_location) as (mock_check_function):

            # Make the call
            constructor(**self.default_args)
            self.assertIn(call(port_to_check, port_name),
                          mock_check_function.call_args_list)

    def do_port_check_reset_test(self, constructor, port_name, active, isasync):
        '''Checks the reset port test was performed on the specified port
        with the given port name.
        '''
        port_to_check = self.default_args[port_name]

        patch_location = constructor.__module__ + '.check_reset_signal'
        with patch(patch_location) as (mock_check_function):

            # Make the call
            constructor(**self.default_args)
            self.assertIn(call(port_to_check, port_name, active=active,
                               isasync=isasync),
                          mock_check_function.call_args_list)


