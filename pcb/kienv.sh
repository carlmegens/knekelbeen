# Source this to use the user-space KiCad in ~/.local/opt/kicad (no sudo install).
# Once KiCad is installed with pacman, this file isn't needed any more.
K=$HOME/.local/opt/kicad/root
if [ -d "$K" ] && ! command -v kicad-cli >/dev/null 2>&1; then
  export PATH=$K/usr/bin:$PATH
  export LD_LIBRARY_PATH=$K/usr/lib:$K/usr/lib/kicad${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
  export PYTHONPATH=$K/usr/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}
  export KICAD10_FOOTPRINT_DIR=$K/usr/share/kicad/footprints
  export KICAD10_SYMBOL_DIR=$K/usr/share/kicad/symbols
  export KICAD10_TEMPLATE_DIR=$K/usr/share/kicad/template
  export KICAD_STOCK_DATA_HOME=$K/usr/share/kicad
fi
