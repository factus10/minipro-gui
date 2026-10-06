"""Long-form help shown in the Help menu and when minipro is missing."""

QUICK_START = """
<h2>Quick start</h2>
<p>minipro GUI drives the <b>minipro</b> command-line tool, which talks to XGecu TL866A/CS,
TL866II+, T48 and T56 programmers. Every button runs one minipro command, and the exact command
is printed in the log at the bottom of the window, so you can always see what happened.</p>

<h3>1&nbsp; Connect the programmer</h3>
<p>Plug in the programmer and click <b>Detect</b> at the top of the window. The programmer
model sets which chips you can choose from. If nothing is connected you can still browse the
chip list - pick your model from the menu next to the Detect button.</p>

<h3>2&nbsp; Choose the chip</h3>
<p>On the <b>Choose chip</b> tab, type the part number printed on the chip and click the matching
entry. If you're not sure what the chip is, put it in the socket and use
<b>Ask the chip in the socket</b>:</p>
<ul>
<li><b>SPI flash</b> (25-series): click <i>Detect 8-pin</i> or <i>Detect 16-pin</i>.</li>
<li><b>Parallel flash and microcontrollers</b>: select any similar part, then click
<i>Read chip ID</i>. The ID the chip reports is looked up across the whole database.</li>
<li><b>EPROMs, EEPROMs, GALs and SRAM</b> can't report an ID - use the part number.</li>
</ul>

<h3>3&nbsp; Program it</h3>
<p>On the <b>Program</b> tab choose an image file and click <b>Write image to chip</b>. Writing
erases the chip first and verifies it afterwards, so you don't need to do those separately.
<b>Read chip to a file</b> makes a backup of a chip.</p>

<h3>4&nbsp; Save a package for repeat jobs</h3>
<p>Click <b>Save as package…</b> to store the chip, image file and options together. On the
<b>Packages</b> tab, select the package and press <b>Program chip</b> (or Ctrl+Enter) for each
new chip. The batch counter shows how many succeeded and failed. Packages can be exported as a
single <i>.minipkg</i> file, which includes the image, and imported on another computer.</p>

<h3>Inserting chips</h3>
<p>Follow your programmer's manual for where a chip sits in the ZIF socket. A chip in the wrong
position or the wrong way round can be damaged. The <b>Pin contact check</b> (TL866II+) tells
you if any pin isn't touching.</p>

<h3>If something fails</h3>
<ul>
<li><b>Chip ID mismatch</b> - the chip isn't the selected part, or isn't seated properly.</li>
<li><b>Incorrect file size</b> - the image is bigger or smaller than the chip. Tick
<i>Allow file size mismatch</i> under Advanced options if that's intended.</li>
<li><b>Verification failed</b> - the chip may be worn out, write-protected (try
<i>Remove write protection first</i>), or a UV EPROM that needs erasing under UV light.</li>
<li><b>Overcurrent protection</b> - remove the chip at once and check its orientation.</li>
</ul>
"""

MINIPRO_MISSING = """
<h3>minipro wasn't found</h3>
<p>This application is a front end for the <b>minipro</b> command-line tool, which needs to be
installed separately.</p>
<ul>
<li><b>macOS (Homebrew):</b> <code>brew install minipro</code></li>
<li><b>Debian/Ubuntu:</b> <code>sudo apt install minipro</code></li>
<li><b>From source:</b>
<a href="https://gitlab.com/DavidGriffith/minipro">gitlab.com/DavidGriffith/minipro</a></li>
</ul>
<p>If it is already installed somewhere unusual, choose <b>Programmer → Locate minipro…</b>
and select the executable.</p>
"""
