#!/usr/bin/python
from subprocess import Popen
import sys
import os
my_env = os.environ.copy()
my_env["PATH"] = f"/usr/sbin:/sbin:{my_env['PATH']}"
filename = sys.argv[1]
while True:
    print("\nStarting " + filename)
    p = Popen("python " + filename, shell=True, env=my_env)
    p.wait()