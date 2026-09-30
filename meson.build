project('webdict', version: '0.1.0', meson_version: '>= 0.62.0')

gnome = import('gnome')
python = import('python').find_installation('python3')

blueprints = custom_target(
  'blueprints',
  input: 'data/ui/window.blp',
  output: 'window.ui',
  command: [find_program('blueprint-compiler'), 'compile', '@INPUT@', '--output', '@OUTPUT@'],
)

resources = gnome.compile_resources(
  'webdict-resources',
  'data/webdict.gresource.xml',
  source_dir: ['data', meson.current_build_dir()],
  dependencies: blueprints,
  gresource_bundle: true,
  install: true,
  install_dir: get_option('datadir') / 'webdict',
)

python.install_sources(
  'webdict/__init__.py',
  'webdict/application.py',
  'webdict/wiktionary.py',
  'webdict/quirks.py',
  subdir: 'webdict',
)

install_data('data/io.github.webdict.Webdict.desktop', install_dir: get_option('datadir') / 'applications')
install_data('data/io.github.webdict.Webdict.metainfo.xml', install_dir: get_option('datadir') / 'metainfo')
install_data('data/icons/io.github.webdict.Webdict.svg', install_dir: get_option('datadir') / 'icons' / 'hicolor' / 'scalable' / 'apps')

configure_file(
  input: 'webdict.in',
  output: 'webdict',
  configuration: {'PYTHON': python.full_path()},
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
