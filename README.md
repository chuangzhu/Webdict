# Webdict

A focused GTK 4/libadwaita dictionary client for multilingual Wiktionary editions.

## Run from source

```sh
meson setup build
meson compile -C build
python3 -m webdict.application
```

For a normal installed build:

```sh
meson setup build --prefix=$HOME/.local
meson install -C build
webdict
```

Webdict uses the standard MediaWiki API of the selected Wiktionary edition—for example,
`fr.wiktionary.org` for French—and is not tied to the English-only API.
