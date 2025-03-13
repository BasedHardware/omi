"""
PyOgg Wrapper Module

This module provides a wrapper for PyOgg that handles the 'c_int_p' issue
without modifying the original library files.
"""

import importlib
import sys
import logging
import types
from ctypes import POINTER, c_int

# Store the original import function
original_import = __import__

def patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    """
    A patched import function that intercepts PyOgg imports and fixes the c_int_p issue.
    """
    # Call the original import function
    module = original_import(name, globals, locals, fromlist, level)

    # Check if we're importing PyOgg's opus module
    if name == 'pyogg.opus' or (name == 'pyogg' and fromlist and 'opus' in fromlist):
        try:
            # Get the opus module
            opus_module = module if name == 'pyogg.opus' else getattr(module, 'opus', None)

            if opus_module and not hasattr(opus_module, 'c_int_p'):
                # Add the missing c_int_p definition
                logging.info("Patching PyOgg opus module with POINTER(c_int) definition")
                setattr(opus_module, 'c_int_p', POINTER(c_int))
                print("✅ Successfully patched PyOgg opus module with POINTER(c_int) definition")
        except Exception as e:
            logging.warning(f"Failed to patch PyOgg opus module: {e}")
            print(f"❌ Failed to patch PyOgg opus module: {e}")

    return module

def install_import_hook():
    """
    Install the import hook to patch PyOgg at runtime.
    """
    sys.meta_path.insert(0, PyOggImportFinder())
    logging.info("PyOgg import hook installed")
    print("🔄 PyOgg import hook installed")

class PyOggImportFinder:
    """
    Import finder that intercepts PyOgg imports.
    """
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith('pyogg'):
            # Let the original import machinery find the module
            return None
        return None

    def find_module(self, fullname, path=None):
        if fullname.startswith('pyogg'):
            return PyOggImportLoader()
        return None

class PyOggImportLoader:
    """
    Import loader that patches PyOgg modules.
    """
    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]

        # Import the module using the original import machinery
        module = original_import(fullname)

        # If it's the opus module, patch it
        if fullname == 'pyogg.opus':
            if not hasattr(module, 'c_int_p'):
                setattr(module, 'c_int_p', POINTER(c_int))
                logging.info(f"Patched {fullname} with POINTER(c_int) definition")
                print(f"✅ Patched {fullname} with POINTER(c_int) definition")

        return module

# Simple function to get a patched OpusDecoder
def get_opus_decoder():
    """
    Get a patched OpusDecoder instance.

    Returns:
        OpusDecoder or None: A patched OpusDecoder instance or None if PyOgg is not available.
    """
    try:
        # In Python 3, __builtin__ is named builtins
        builtins_module = sys.modules.get('builtins')

        if builtins_module:
            # Save the original import
            original = builtins_module.__import__

            # Patch the import system
            builtins_module.__import__ = patched_import

            try:
                # Import OpusDecoder
                from pyogg import OpusDecoder
                decoder = OpusDecoder()
                print("✅ Successfully imported OpusDecoder with patched PyOgg")
                return decoder
            finally:
                # Restore the original import function
                builtins_module.__import__ = original
        else:
            # Alternative approach: monkey patch the opus module directly
            import pyogg.opus
            if not hasattr(pyogg.opus, 'c_int_p'):
                pyogg.opus.c_int_p = POINTER(c_int)
                logging.info("Directly patched pyogg.opus module with POINTER(c_int) definition")
                print("✅ Directly patched pyogg.opus module with POINTER(c_int) definition")

            from pyogg import OpusDecoder
            print("✅ Successfully imported OpusDecoder with directly patched PyOgg")
            return OpusDecoder()

    except (ImportError, AttributeError) as e:
        logging.warning(f"Failed to import OpusDecoder: {e}")
        print(f"❌ Failed to import OpusDecoder: {e}")
        return None
    except Exception as e:
        logging.warning(f"Unexpected error importing OpusDecoder: {e}")
        print(f"❌ Unexpected error importing OpusDecoder: {e}")
        return None