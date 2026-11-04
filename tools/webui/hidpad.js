"use strict";

// WebHID session with the pad. Chrome and Edge only. No local server.
// Report id 3, 15 payload bytes. The report id itself is not in the DataView.

(function () {
  const B = globalThis.PadBind;
  let device = null;
  let info = null;
  let chain = Promise.resolve();

  function exclusive(fn) {
    const run = chain.then(fn, fn);
    chain = run.then(() => {}, () => {});
    return run;
  }

  function opened() {
    return !!(device && device.opened);
  }

  function waitReport(cmd, ms) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        device.removeEventListener("inputreport", onReport);
        reject(new Error("The pad did not answer. If it no longer shows up as a keyboard, use chflash with the full image."));
      }, ms);
      function onReport(event) {
        if (event.reportId !== B.REPORT) return;
        const view = event.data;
        if (view.getUint8(0) !== cmd) return;
        clearTimeout(timer);
        device.removeEventListener("inputreport", onReport);
        resolve(view);
      }
      device.addEventListener("inputreport", onReport);
    });
  }

  function transact(cmd, extra, ms) {
    return exclusive(async () => {
      if (!opened()) throw new Error("The pad is not connected.");
      const pending = waitReport(cmd, ms || 1000);
      await device.sendReport(B.REPORT, B.buildReport(cmd, extra));
      return pending;
    });
  }

  function configStatus(view) {
    // Firmware status lives in buffer byte 7. WebHID byte 0 is buffer byte 1.
    return view.byteLength > 6 ? view.getUint8(6) : 0;
  }

  function requireOk(view) {
    const status = configStatus(view);
    if (status !== B.ST_OK) {
      throw new Error(B.STATUS[status] || `the pad returned status ${status}`);
    }
  }

  async function readInfo() {
    const view = await transact(B.CMD_GET_INFO, null, 1000);
    if (view.getUint8(1) !== 0x50 || view.getUint8(2) !== 0x44) {
      throw new Error("The pad answered, but it was not the configuration report.");
    }
    requireOk(view);
    const firmware = `${view.getUint8(7)}.${view.getUint8(8)}.${view.getUint8(9)}`;
    const hostByte = view.byteLength > 10 ? view.getUint8(10) : 0;
    info = {
      format: view.getUint8(3),
      count: view.getUint8(4),
      flash: view.getUint8(5),
      firmware,
      host: B.supportsHost(firmware) ? B.unpackProfile(hostByte) : { layout: "us", os: "windows", confirmed: false },
      supported: B.supportsHost(firmware),
      canUpdate: B.canUpdate(firmware),
    };
    return info;
  }

  async function readSlots() {
    const slots = [];
    for (let i = 0; i < B.SLOTS.length; i++) {
      const view = await transact(B.CMD_GET_ACTION, [i], 1000);
      requireOk(view);
      const action = {
        type: view.getUint8(2),
        mod: view.getUint8(3),
        code: view.getUint8(4) | (view.getUint8(5) << 8),
      };
      const id = B.SLOTS[i];
      slots.push({
        id,
        label: B.slotLabel(id),
        group: /^\d+$/.test(id) ? "key" : "knob",
        binding: B.stringify(action),
      });
    }
    return slots;
  }

  async function readConfig() {
    const current = await readInfo();
    const slots = await readSlots();
    return { ...current, slots };
  }

  async function connect() {
    if (!navigator.hid) {
      throw new Error("This browser has no WebHID. Use Chrome or Edge.");
    }
    const devices = await navigator.hid.requestDevice({
      filters: [{ vendorId: B.VID, productId: B.PID, usagePage: 0xFF00 }],
    });
    const next = devices && devices[0];
    if (!next) throw new Error("No pad was chosen.");
    if (device && device !== next && device.opened) {
      try { await device.close(); } catch (err) { /* already gone */ }
    }
    device = next;
    if (!device.opened) await device.open();
    return device;
  }

  async function writeChanges(changes) {
    for (const [id, spec] of Object.entries(changes)) {
      const idx = B.SLOTS.indexOf(id);
      if (idx < 0) throw new Error(`Unknown slot '${id}'`);
      const action = B.parse(spec);
      const view = await transact(B.CMD_SET_ACTION, [
        idx, action.type, action.mod, action.code & 0xFF, (action.code >> 8) & 0xFF,
      ], 1000);
      requireOk(view);
    }
    return readSlots();
  }

  async function setHost(layout, osName) {
    const byte = B.packProfile(layout, osName);
    const view = await transact(B.CMD_SET_HOST, [byte], 1000);
    requireOk(view);
    return readInfo();
  }

  async function reset() {
    const view = await transact(B.CMD_RESET, null, 1500);
    requireOk(view);
    return readSlots();
  }

  async function bootloader() {
    await transact(B.CMD_BOOTLOADER, null, 800).catch(() => {});
    device = null;
  }

  globalThis.HidPad = {
    connect, opened, readConfig, writeChanges, setHost, reset, bootloader, transact,
    device: () => device,
    info: () => info,
  };
})();
