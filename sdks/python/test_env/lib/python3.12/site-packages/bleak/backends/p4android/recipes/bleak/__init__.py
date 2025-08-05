import os
from os.path import join

import sh
from pythonforandroid.recipe import PythonRecipe
from pythonforandroid.toolchain import info, shprint


class BleakRecipe(PythonRecipe):
    version = None  # Must be none for p4a to correctly clone repo
    fix_setup_py_version = "bleak develop branch"
    url = "git+https://github.com/hbldh/bleak.git"
    name = "bleak"

    depends = ["pyjnius"]
    call_hostpython_via_targetpython = False

    fix_setup_filename = "fix_setup.py"

    def prepare_build_dir(self, arch):
        super().prepare_build_dir(arch)  # Unpack the url file to the get_build_dir
        build_dir = self.get_build_dir(arch)

        setup_py_path = join(build_dir, "setup.py")
        if not os.path.exists(setup_py_path):
            # Perform the p4a temporary fix
            # At the moment, p4a recipe installing requires setup.py to be present
            # So, we create a setup.py file only for android

            fix_setup_py_path = join(self.get_recipe_dir(), self.fix_setup_filename)
            with open(fix_setup_py_path, "r") as f:
                contents = f.read()

            # Write to the correct location and fill in the version number
            with open(setup_py_path, "w") as f:
                f.write(contents.replace("[VERSION]", self.fix_setup_py_version))
        else:
            info("setup.py found in bleak directory, are you installing older version?")

    def get_recipe_env(self, arch=None, with_flags_in_cc=True):
        env = super().get_recipe_env(arch, with_flags_in_cc)
        # to find jnius and identify p4a
        env["PYJNIUS_PACKAGES"] = self.ctx.get_site_packages_dir(arch)
        return env

    def postbuild_arch(self, arch):
        super().postbuild_arch(arch)

        info("Copying java files")
        dest_dir = self.ctx.javaclass_dir
        path = join(
            self.get_build_dir(arch.arch), "bleak", "backends", "p4android", "java", "."
        )

        shprint(sh.cp, "-a", path, dest_dir)


recipe = BleakRecipe()
