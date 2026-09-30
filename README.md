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

## Build the Flatpak

```sh
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.gnome.Platform//51 org.gnome.Sdk//51
flatpak-builder --user --install --force-clean build-flatpak cz.chuang.Webdict.yml
flatpak run cz.chuang.Webdict
```
