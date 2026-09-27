{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  packages = with pkgs; [
    (python3.withPackages (pythonPackages: with pythonPackages; [
      pygobject3
    ]))

    gtk4
    libadwaita
    gobject-introspection

    meson
    ninja
    blueprint-compiler
    adwaita-icon-theme

    # Common tools used while developing and packaging GTK applications.
    pkg-config
    gettext
    desktop-file-utils
  ];

  # Makes GTK/libadwaita GSettings schemas and other shared data visible when
  # running the application directly from this development shell.
  shellHook = ''
    export XDG_DATA_DIRS="${pkgs.gtk4}/share:${pkgs.libadwaita}/share''${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
  '';
}
