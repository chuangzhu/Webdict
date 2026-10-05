project('webdict', version: '0.1.0', meson_version: '>= 0.62.0')

gnome = import('gnome')
i18n = import('i18n')
python = import('python').find_installation('python3')

subdir('po')
subdir('data')

test(
  'unit',
  python,
  args: ['-m', 'unittest', 'discover', '-s', 'tests', '-v'],
  workdir: meson.current_source_dir(),
  depends: schemas,
  env: {'GSETTINGS_SCHEMA_DIR': meson.current_build_dir() / 'data'},
)
gnome.post_install(glib_compile_schemas: true)

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
  'webdict/edition_dropdown.py',
  'webdict/result_text.py',
  'webdict/wiktionary.py',
  'webdict/quirks.py',
  'webdict/i18n.py',
  subdir: 'webdict',
)

install_data('data/cz.chuang.Webdict.desktop', install_dir: get_option('datadir') / 'applications')
install_data('data/cz.chuang.Webdict.metainfo.xml', install_dir: get_option('datadir') / 'metainfo')
install_data('data/icons/cz.chuang.Webdict.svg', install_dir: get_option('datadir') / 'icons' / 'hicolor' / 'scalable' / 'apps')

configure_file(
  input: 'webdict.in',
  output: 'webdict',
  configuration: {
    'PYTHON': python.full_path(),
    'LOCALEDIR': get_option('prefix') / get_option('localedir'),
    'RESOURCEFILE': get_option('prefix') / get_option('datadir') / 'webdict' / 'webdict-resources.gresource',
  },
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
