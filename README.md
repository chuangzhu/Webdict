<img width="60" alt="logo" src="https://github.com/user-attachments/assets/8b52940f-6c53-4185-a569-e1d5157ca36d">

# Webdict

A focused GTK 4/libadwaita dictionary client for multilingual Wiktionary editions.

![Screenshot](https://github.com/user-attachments/assets/66145b1f-22c3-4216-b1b2-97bc504362fc)

Webdict uses the standard MediaWiki API of the selected Wiktionary edition—for example,
`fr.wiktionary.org` for French—and is not tied to the English-only API.

## Run from source

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
