# Webdict

A focused GTK 4/libadwaita dictionary client for multilingual Wiktionary editions.

Webdict uses the standard MediaWiki API of the selected Wiktionary edition—for example,
`fr.wiktionary.org` for French—and is not tied to the English-only API.

## Run from source

```sh
meson setup build
meson compile -C build
python3 -m webdict.application
```

For a normal installed build:

```sh
prefix=$(mktemp -d)
export XDG_DATA_DIRS=$XDG_DATA_DIRS:$prefix/share PYTHONPATH=$PYTHONPATH:$prefix/lib/python3.13/site-packages PATH=$PATH:$prefix/bin
meson setup build --prefix=$prefix
meson install -C build
webdict
```
