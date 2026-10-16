// Adds the carrier board parts (pcb/README.md) to your TinyTronics cart.
// Open https://www.tinytronics.nl in your browser, press F12, go to Console,
// paste this whole file and press Enter. Product IDs checked on 2026-10-13.
(async () => {
  const parts = [
    [1253, 2, "40 pins header female, white"],
    [160, 1, "40 pins header male"],
    [3161, 1, "SN74AHCT125N"],
    [642, 1, "14 pins IC socket"],
    [170, 3, "2 pin screw terminal 5.08 mm"],
    [375, 1, "microSD module with level shifter"],
    [1839, 1, "PTC fuse 5000 mA through hole"],
    [4171, 1, "1N5822 Schottky"],
    [394, 1, "Diode set 100 pieces (1N5819 for D2)"],
    [8079, 1, "1000 uF 25 V, 5 pieces"],
    [8081, 1, "470 uF 25 V, 5 pieces"],
    [226, 1, "100 nF ceramic"],
    [7621, 1, "1 kOhm, 10 pieces"],
    [7619, 1, "330 Ohm, 10 pieces"],
    [1132, 2, "Green LED 3 mm diffused"],
    [1950, 1, "M3 spacer kit"],
  ];
  for (const [id, qty, name] of parts) {
    try {
      const r = await fetch("/index.php?route=checkout/cart/add", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                   "X-Requested-With": "XMLHttpRequest" },
        body: `product_id=${id}&quantity=${qty}`,
      });
      const text = await r.text();
      let ok = r.ok;
      try { const j = JSON.parse(text); ok = !!j.success && !j.error; } catch {}
      console.log(`${ok ? "OK  " : "FAIL"} ${qty}x ${name}`, ok ? "" : text.slice(0, 200));
    } catch (e) {
      console.log(`FAIL ${qty}x ${name}`, e);
    }
  }
  console.log("Done. Opening the cart...");
  location.href = "/index.php?route=checkout/cart";
})();
