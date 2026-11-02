"use strict";

// Vendor-HID firmware update. The browser talks to the pad directly; the
// Python server is not on this path. Report id 3, payload without the id byte.
// Firmware layout after the id: cmd, status, detail_lo, detail_hi.

const VID = 0x1189;
const PID = 0x8890;
const REPORT = 3;
const CMD_GET_INFO = 0x01;
const CMD_INFO = 0x10;
const CMD_BEGIN = 0x11;
const CMD_DATA = 0x12;
const CMD_COMMIT = 0x13;
const DATA = 12;
const ST_OK = 1;
// One-time image. 1.0.0 and 1.1.0 have no updater command, so this is chflash.
const FULL_IMAGE = "firmware/prebuilt/padfw-1.2.0.bin";
const FULL_BYTES = 13296;

let hid = null;
let image = null;
let padVersion = null;
let padCanUpdate = false;

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
      // WebHID drops the report id, so byte 0 is the firmware's byte 1.
      if (view.getUint8(0) !== cmd) return;
      clearTimeout(timer);
      hid.removeEventListener("inputreport", onReport);
      resolve(view);
    }
    hid.addEventListener("inputreport", onReport);
  });
}

// 1.0.0 and 1.1.0 answer an unknown command with a zeroed buffer and the
// command echoed. The updater reads its status from byte 1 of that view,
// which stays 0. That is not ST_OK (1) and not an updater error code.
// GET_INFO (0x01) is implemented on those builds; its version is bytes 7-9.
function firmwareVersion(view) {
  if (view.byteLength < 10) return null;
  if (view.getUint8(1) !== 0x50 || view.getUint8(2) !== 0x44) return null;
  return `${view.getUint8(7)}.${view.getUint8(8)}.${view.getUint8(9)}`;
}

function olderThanUpdater(version) {
  const [major, minor] = version.split(".").map((n) => Number(n));
  return major < 1 || (major === 1 && minor < 2);
}

function chflashMessage(version) {
  return `This pad is firmware ${version}. It has no browser updater, so Connect and Update firmware stop here. ` +
    `Flash the full image once: python tools/chflash.py ${FULL_IMAGE} --wait 30 ` +
    `(${FULL_BYTES} bytes). Start that command, then reboot into the bootloader. ` +
    `The .web.bin is for a pad that is already running 1.2.0.`;
}

async function transact(cmd, extra, ms) {
  const pending = waitReport(cmd, ms);
  await hid.sendReport(REPORT, payload(cmd, extra));
  const view = await pending;
  const reply = {
    status: view.getUint8(1),
    detail: view.getUint8(2) | (view.getUint8(3) << 8),
  };
  if (reply.status !== ST_OK) {
    const why = {
      3: "the pad rejected the image",
      4: "the pad could not write flash",
      5: "the pad is not ready for that command",
      6: "the image checksum did not match",
      7: "the image is not a bootable .web.bin (wrong size, or the USB jump is not at offset 0x43)",
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
  padVersion = null;
  padCanUpdate = false;
  let version = null;
  try {
    const pending = waitReport(CMD_GET_INFO, 1000);
    await hid.sendReport(REPORT, payload(CMD_GET_INFO));
    version = firmwareVersion(await pending);
  } catch (err) {
    fwNote(err.message, "bad");
    return;
  }
  padVersion = version;
  if (version && olderThanUpdater(version)) {
    fwNote(chflashMessage(version), "warn");
    fw("fwGo").disabled = false;
    return;
  }
  try {
    const info = await transact(CMD_INFO, null, 1000);
    padCanUpdate = true;
    fwNote(`Updater ready on firmware ${version || "1.2.0"}. Largest image is ${info.detail} bytes.`, "good");
    fw("fwGo").disabled = !image;
  } catch (err) {
    // Status 0 here is the empty reply from a pad with no updater command.
    // A 1.2.0 pad returns status 1 for this same command.
    if (err.reply && err.reply.status === 0) {
      fwNote(chflashMessage(version || "1.0.0 or 1.1.0"), "warn");
      fw("fwGo").disabled = false;
      return;
    }
    fwNote(err.message, "bad");
  }
}

async function runUpdate() {
  if (!hid || !image) return;
  if (!padCanUpdate) {
    fwNote(chflashMessage(padVersion || "1.0.0 or 1.1.0"), "warn");
    return;
  }
  fw("fwGo").disabled = true;
  const bar = fw("fwProgress");
  bar.max = image.length;
  bar.value = 0;
  if (image.length < 0x400 || image.length > 0x2000) {
    fwNote(`Image is ${image.length} bytes. Choose padfw-1.2.0.web.bin, not the full recovery file.`, "bad");
    fw("fwGo").disabled = false;
    return;
  }
  const trampoline = image[0] === 0x02 && image[1] === 0x24 && image[2] === 0x00 &&
    image[0x43] === 0x02 && image[0x44] === 0x24 && image[0x45] === 0x03;
  if (!trampoline) {
    fwNote("This file would not enumerate. Use the rebuilt padfw-1.2.0.web.bin (USB jump at offset 0x43), not an older copy or the full .bin.", "bad");
    fw("fwGo").disabled = false;
    return;
  }
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
    if (err.reply && err.reply.status === 0) {
      fwNote(chflashMessage(padVersion || "1.0.0 or 1.1.0"), "warn");
    } else {
      fwNote(err.message, "bad");
    }
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
    if (hid && !padCanUpdate) {
      fwNote(`${chflashMessage(padVersion || "1.0.0 or 1.1.0")} Selected ${file.name} (${image.length} bytes) stays on the computer.`, "warn");
    } else {
      fwNote(`${file.name}, ${image.length} bytes.`, "");
    }
    fw("fwGo").disabled = !hid;
  });
};
fw("fwGo").onclick = () => {
  runUpdate().catch((err) => fwNote(err.message, "bad"));
};
