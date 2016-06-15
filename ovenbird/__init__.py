from distutils import spawn as _spawn
VIVADO_EXECUTABLE = _spawn.find_executable('vivado')

from .cosimulation import *
from .vivado_ip import *

import myhdl as _myhdl
class OvenbirdConversionError(_myhdl.ConversionError):
    pass
