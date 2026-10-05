{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  packages = with pkgs; [
    (python3.withPackages (pythonPackages: with pythonPackages; [
      pygobject3
    ]))

    gtk4
    libadwaita
    gobject-introspection
    gst_all_1.gstreamer
    gst_all_1.gst-plugins-base
    gst_all_1.gst-plugins-good
    gst_all_1.gst-plugins-bad
    gst_all_1.gst-libav

    meson
    ninja
    blueprint-compiler
    adwaita-icon-theme

    # Common tools used while developing and packaging GTK applications.
    pkg-config
    gettext
    desktop-file-utils

  ] ++ lib.optionals stdenv.hostPlatform.isLinux [
    flatpak
    flatpak-builder
    appstream
  ];
}
