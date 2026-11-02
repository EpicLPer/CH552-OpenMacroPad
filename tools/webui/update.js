"use strict";

// Vendor-HID firmware update. The browser talks to the pad directly; the
// Python server is not on this path. Report id 3, payload without the id byte.
// Firmware layout after the id: cmd, status, detail_lo, detail_hi.

const VID = 0x1189;
const PID = 0x8890;
const REPORT = 3;
const CMD_INFO = 0x10;
const CMD_BEGIN = 0x11;
const CMD_DATA = 0x12;
const CMD_COMMIT = 0x13;
const DATA = 12;
const ST_OK = 1;

let hid = null;
let image = null;

const fw = (id) => document.getElementById(id);

function fwNote(text, cls) {
  const n = fw("fwNote");
  n.textContent = text;
  n.className = `hint ${cls || ""}`;
}

function crc32(bytes) {
  let crc = 0xFFFFFFFF;
  for (const b of bytes) {
    crc ^= b;
    for (let i = 0; i < 8; i++) {
      crc = (crc >>> 1) ^ ((crc & 1) ? 0xEDB88320 : 0);
    }
  }
  return (~crc) >>> 0;
}

function payload(cmd, extra) {
  const data = new Uint8Array(15);
  data[0] = cmd;
  if (extra) data.set(extra, 1);
  return data;
}

function waitReport(cmd, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      hid.removeEventListener("inputreport", onReport);
      reject(new Error("The pad did not answer. If it no longer shows up as a keyboard, use the recovery image and chflash."));
    }, ms);
    function onReport(event) {
      if (event.reportId !== REPORT) return;
      const view = event.data;
      if (view.getUint8(0) !== cmd) return;
      clearTimeout(timer);
      hid.removeEventListener("inputreport", onReport);
      resolve({
        status: view.getUint8(1),
        detail: view.getUint8(2) | (view.getUint8(3) << 8),
      });
    }
    hid.addEventListener("inputreport", onReport);
  });
}

async function transact(cmd, extra, ms) {
  const pending = waitReport(cmd, ms);
  await hid.sendReport(REPORT, payload(cmd, extra));
  const reply = await pending;
  if (reply.status !== ST_OK) {
    const why = {
      3: "the pad rejected the image",
      4: "the pad could not write flash",
      5: "the pad is not ready for that command",
      6: "the image checksum did not match",
      7: "the image is the wrong size (use the .web.bin, not the full recovery file)",
    }[reply.status] || `status ${reply.status}`;
    const err = new Error(why);
    err.reply = reply;
    throw err;
  }
  return reply;
}

async function connectHid() {
  if (!navigator.hid) {
    fwNote("This browser has no WebHID. Use Chrome or Edge.", "bad");
    return;
  }
  const devices = await navigator.hid.requestDevice({
    filters: [{ vendorId: VID, productId: PID, usagePage: 0xFF00 }],
  });
  hid = devices[0];
  if (!hid) return;
  if (!hid.opened) await hid.open();
  try {
    const info = await transact(CMD_INFO, null, 1000);
    fwNote(`Updater ready. Largest image is ${info.detail} bytes.`, "good");
    fw("fwGo").disabled = !image;
  } catch (err) {
    fwNote(`${err.message} A 1.0.0 or 1.1.0 pad needs the one-time chflash first.`, "warn");
  }
}

async function runUpdate() {
  if (!hid || !image) return;
  fw("fwGo").disabled = true;
  const bar = fw("fwProgress");
  bar.max = image.length;
  bar.value = 0;
  const crc = crc32(image);
  const begin = new Uint8Array(6);
  begin[0] = image.length & 0xFF;
  begin[1] = image.length >> 8;
  begin[2] = crc & 0xFF;
  begin[3] = (crc >> 8) & 0xFF;
  begin[4] = (crc >> 16) & 0xFF;
  begin[5] = (crc >> 24) & 0xFF;
  try {
    const started = await transact(CMD_BEGIN, begin, 3000);
    if (image.length > started.detail) {
      throw new Error(`Image is ${image.length} bytes; this pad accepts ${started.detail}. Use the .web.bin file.`);
    }
    for (let off = 0; off < image.length; off += DATA) {
      const chunk = image.subarray(off, Math.min(image.length, off + DATA));
      const body = new Uint8Array(2 + DATA);
      body[0] = off & 0xFF;
      body[1] = off >> 8;
      body.set(chunk, 2);
      await transact(CMD_DATA, body, 3000);
      bar.value = Math.min(image.length, off + DATA);
      fwNote(`Writing ${bar.value} / ${image.length}`, "");
    }
    fwNote("Checking the image and restarting the pad…", "");
    await transact(CMD_COMMIT, null, 5000);
    fwNote("Update accepted. The pad is rebooting. Reconnect it to set the keyboard layout.", "good");
  } catch (err) {
    fwNote(err.message, "bad");
    fw("fwGo").disabled = false;
  }
}

fw("fwConnect").onclick = () => {
  connectHid().catch((err) => fwNote(err.message, "bad"));
};
fw("fwFile").onchange = () => {
  const file = fw("fwFile").files[0];
  if (!file) return;
  file.arrayBuffer().then((buf) => {
    image = new Uint8Array(buf);
    fwNote(`${file.name}, ${image.length} bytes.`, "");
    fw("fwGo").disabled = !hid;
  });
};
fw("fwGo").onclick = () => {
  runUpdate().catch((err) => fwNote(err.message, "bad"));
};
