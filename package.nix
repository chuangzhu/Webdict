{
  lib,
  python3,
  gtk4,
  libadwaita,
  gobject-introspection,
  gst_all_1,
  meson,
  pkg-config,
  ninja,
  gettext,
  glib,
  desktop-file-utils,
  blueprint-compiler,
  wrapGAppsHook4,
  # unstableGitUpdater,
}:

python3.pkgs.buildPythonApplication {
  pname = "webdict";
  version = "0.1.0-unstable-2026-09-30";

  format = "other";

  src = ./.;

  nativeBuildInputs = [
    meson
    pkg-config
    ninja
    gettext
    glib
    desktop-file-utils
    blueprint-compiler
    wrapGAppsHook4
  ];

  buildInputs = [
    gtk4
    libadwaita
    gobject-introspection
    gst_all_1.gstreamer
    gst_all_1.gst-plugins-base
    gst_all_1.gst-plugins-good
    gst_all_1.gst-plugins-bad
    gst_all_1.gst-libav
  ];

  propagatedBuildInputs = with python3.pkgs; [
    pygobject3
  ];

  # Prevent double wrapping.
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
    )
  '';

  # passthru.updateScript = unstableGitUpdater {
  #   url = src.gitRepoUrl;
  #   hardcodeZeroVersion = true;
  # };

  meta = {
    description = "Focused GTK 4/libadwaita dictionary client for multilingual Wiktionary editions";
    homepage = "https://github.com/chuangzhu/Webdict";
    license = lib.licenses.gpl3Plus;
    maintainers = with lib.maintainers; [ chuangzhu ];
  };
}
