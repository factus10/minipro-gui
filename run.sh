#!/bin/sh
# Launch minipro GUI from a source checkout.
#
# On some Macs the files inside .venv pick up the "hidden" file flag (seen in
# iCloud-synced folders). Python then skips the venv's .pth files and Qt can't
# find its platform plugins, so clear the flag before starting.
cd "$(dirname "$0")" || exit 1
[ "$(uname)" = Darwin ] && [ -d .venv ] && chflags -R nohidden .venv 2>/dev/null
exec uv run python -m minipro_gui "$@"
