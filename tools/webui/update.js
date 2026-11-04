"use strict";

// Firmware update over the same WebHID connection as the keymap.
// Report id 3. After the id is stripped: cmd, status, detail_lo, detail_hi.

const CMD_INFO = 0x10;
const CMD_BEGIN = 0x11;
const CMD_DATA = 0x12;
const CMD_COMMIT = 0x13;
const DATA = 12;
const ST_OK = 1;
const FULL_IMAGE = "firmware/prebuilt/padfw-1.2.2.bin";
const FULL_BYTES = 13376;

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

function chflashMessage(version) {
  return `Pad firmware ${version}. Flash the full file once: python tools/chflash.py ${FULL_IMAGE} --wait 30`;
}

async function transact(cmd, extra, ms) {
  const view = await HidPad.transact(cmd, extra, ms);
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

function noteFirmware(data) {
  padVersion = data.firmware;
  padCanUpdate = !!data.canUpdate;
  if (!padCanUpdate) {
    fwNote(chflashMessage(data.firmware), "warn");
    fw("fwGo").disabled = true;
    return;
  }
  fwNote(image ? `${image.length} bytes.` : "Choose the .web.bin file.", "good");
  fw("fwGo").disabled = !image;
}

globalThis.onPadConnected = noteFirmware;

async function runUpdate() {
  if (!image) return;
  if (!HidPad.opened()) {
    fwNote("Connect the pad first.", "warn");
    return;
  }
  if (!padCanUpdate) {
    fwNote(chflashMessage(padVersion || "1.0.0 or 1.1.0"), "warn");
    return;
  }
  fw("fwGo").disabled = true;
  const bar = fw("fwProgress");
  bar.max = image.length;
  bar.value = 0;
  if (image.length < 0x400 || image.length > 0x2000) {
    fwNote("Use the .web.bin file, not the full .bin.", "bad");
    fw("fwGo").disabled = false;
    return;
  }
  const trampoline = image[0] === 0x02 && image[1] === 0x24 && image[2] === 0x00 &&
    image[0x43] === 0x02 && image[0x44] === 0x24 && image[0x45] === 0x03;
  if (!trampoline) {
    fwNote("That file cannot be used. Choose the .web.bin file.", "bad");
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
      throw new Error("Use the .web.bin file.");
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
    fwNote("Checking…", "");
    await transact(CMD_COMMIT, null, 5000);
    fwNote("Updated. Connect again.", "good");
  } catch (err) {
    if (err.reply && err.reply.status === 0) {
      fwNote(chflashMessage(padVersion || "1.0.0 or 1.1.0"), "warn");
    } else {
      fwNote(err.message, "bad");
    }
    fw("fwGo").disabled = false;
  }
}

fw("fwFile").onchange = () => {
  const file = fw("fwFile").files[0];
  if (!file) return;
  file.arrayBuffer().then((buf) => {
    image = new Uint8Array(buf);
    if (HidPad.opened() && !padCanUpdate) {
      fwNote(chflashMessage(padVersion || "older"), "warn");
    } else {
      fwNote(`${file.name}, ${image.length} bytes.`, "");
    }
    fw("fwGo").disabled = !(HidPad.opened() && padCanUpdate);
  });
};
fw("fwGo").onclick = () => {
  runUpdate().catch((err) => fwNote(err.message, "bad"));
};
