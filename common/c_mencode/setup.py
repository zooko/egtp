import sys
import os
# distutils is included with python 1.6 and later, go grab a if you use python 1.5.2.
from distutils.core import setup, Extension

setup ( name = "_c_mencode_help",
        version = "1.0",
        author = "Autonomous Zone Industries",
        author_email = "mojonation-devel@lists.sourceforge.net",
        ext_modules = [
            Extension(
                "_c_mencode_help",
                ["_c_mencode_help.c"],
                include_dirs=[os.path.join(sys.prefix, 'PC')],
            )
        ],
      )

