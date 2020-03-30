#! /usr/bin/python
# by pts@fazekas.hu at Thu Nov  2 15:09:49 CET 2017

"""Generates standalone scripts by embedding modules.

* Generates mediafileinfo.py from mediafileinfo_main.py, embedding
  mediafileinfo_detect.py as a module.
* Generates media_scan.py from media_scan_main.py, embedding
  mediafileinfo_detect.py as a module.
"""

import os
import sys


def indent(data, prefix='  '):
  output = []
  for line in data.split('\n'):
    if line and not line.isspace():
      output.append(prefix)
    output.append(line)
    output.append('\n')
  output.pop()
  return ''.join(output)


assert '  foo\n   bar\n\n\t\n  baz' == indent('foo\n bar\n\n\t\nbaz')


MODULE_DECORATOR = r'''
def module(f):
  """Decorator to create a new module from a function."""
  import sys
  assert f.func_name not in sys.modules, f.func_name
  sys.modules[f.func_name] = new_module = type(sys)(f.func_name)
  new_module.__dict__.update(eval(f.func_code, new_module.__dict__))
  return new_module

'''


def main(argv):
  if len(argv) > 1:
    sys.exit('fatal: too many command-line arguments')
  modules_to_embed = ('mediafileinfo_detect', 'mediafileinfo_formatdb')
  main_filenames = ('mediafileinfo.py', 'media_scan.py')

  modules = {}
  module_imports = set()
  for module_name in modules_to_embed:
    assert not module_name.endswith('.py')
    module_filename = module_name + '.py'
    module_data = open(module_filename).read()
    modules[module_name] = '@module\ndef %s():\n%s' % (
        module_name, indent(module_data.strip() + '\n\nreturn locals()\n'))
    module_imports.add('import ' + module_name)

  for main_filename in main_filenames:
    assert main_filename.endswith('.py')
    main_input_filename = (
        main_filename[:main_filename.rfind('.')] + '_main.py')
    main_data = open(main_input_filename).read()
    main_output = []
    decorator = MODULE_DECORATOR
    for line in main_data.split('\n'):
      if line in module_imports:
        if decorator:
          main_output.append(decorator)
          decorator = None
        line = modules[line.split(' ', 1)[1]]
      main_output.append(line)
    main_data = '\n'.join(main_output)
    open(main_filename, 'w').write(main_data)
    os.chmod(main_filename, 0755)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
