/**
 * 纯原生 JavaScript 实现轻量级 ZIP 归档打包器（零外部依赖，纯 ES6）。
 * 用于在浏览器端直接生成符合 IDPF 国际标准的 EPUB 3.0 二进制电子书包。
 */

export class MiniZip {
  constructor() {
    this.files = [];
  }

  // 添加文件，支持 text 或 Uint8Array 二进制内容
  addFile(path, content, isBinary = false, storeOnly = false) {
    let data;
    if (isBinary && content instanceof Uint8Array) {
      data = content;
    } else {
      const encoder = new TextEncoder();
      data = encoder.encode(typeof content === 'string' ? content : String(content));
    }
    this.files.push({
      path,
      data,
      storeOnly: !!storeOnly, // storeOnly 为 true 时压缩方式为 0 (Stored，如 mimetype 必须未压缩)
    });
  }

  // CRC32 计算表
  static _makeCRCTable() {
    let c;
    const table = [];
    for (let n = 0; n < 256; n++) {
      c = n;
      for (let k = 0; k < 8; k++) {
        c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      }
      table[n] = c;
    }
    return table;
  }

  static crc32(data) {
    if (!MiniZip._crcTable) {
      MiniZip._crcTable = MiniZip._makeCRCTable();
    }
    const table = MiniZip._crcTable;
    let crc = 0 ^ (-1);
    for (let i = 0; i < data.length; i++) {
      crc = (crc >>> 8) ^ table[(crc ^ data[i]) & 0xFF];
    }
    return (crc ^ (-1)) >>> 0;
  }

  // 生成 Uint8Array 二进制 Blob
  build() {
    const encoder = new TextEncoder();
    const localHeaders = [];
    const centralHeaders = [];
    let offset = 0;

    for (const file of this.files) {
      const pathBytes = encoder.encode(file.path);
      const crc = MiniZip.crc32(file.data);
      const size = file.data.length;

      // 1. Local File Header (30 字节 + 路径)
      const lfh = new Uint8Array(30 + pathBytes.length);
      const lfhView = new DataView(lfh.buffer);

      lfhView.setUint32(0, 0x04034b50, true); // Local file header signature
      lfhView.setUint16(4, 20, true);         // Version needed to extract
      lfhView.setUint16(6, 0, true);          // General purpose bit flag
      lfhView.setUint16(8, 0, true);          // Compression method: 0 (Stored)
      lfhView.setUint16(10, 0x4821, true);    // Last mod file time
      lfhView.setUint16(12, 0x5555, true);    // Last mod file date
      lfhView.setUint32(14, crc, true);       // CRC-32
      lfhView.setUint32(18, size, true);      // Compressed size
      lfhView.setUint32(22, size, true);      // Uncompressed size
      lfhView.setUint16(26, pathBytes.length, true); // File name length
      lfhView.setUint16(28, 0, true);         // Extra field length
      lfh.set(pathBytes, 30);

      localHeaders.push({ lfh, data: file.data, offset });

      // 2. Central Directory Header (46 字节 + 路径)
      const cdh = new Uint8Array(46 + pathBytes.length);
      const cdhView = new DataView(cdh.buffer);

      cdhView.setUint32(0, 0x02014b50, true); // Central directory header signature
      cdhView.setUint16(4, 20, true);         // Version made by
      cdhView.setUint16(6, 20, true);         // Version needed to extract
      cdhView.setUint16(8, 0, true);          // General purpose bit flag
      cdhView.setUint16(10, 0, true);         // Compression method: 0
      cdhView.setUint16(12, 0x4821, true);    // Last mod file time
      cdhView.setUint16(14, 0x5555, true);    // Last mod file date
      cdhView.setUint32(16, crc, true);       // CRC-32
      cdhView.setUint32(20, size, true);      // Compressed size
      cdhView.setUint32(24, size, true);      // Uncompressed size
      cdhView.setUint16(28, pathBytes.length, true); // File name length
      cdhView.setUint16(30, 0, true);         // Extra field length
      cdhView.setUint16(32, 0, true);         // File comment length
      cdhView.setUint16(34, 0, true);         // Disk number start
      cdhView.setUint16(36, 0, true);         // Internal file attributes
      cdhView.setUint32(38, 0, true);         // External file attributes
      cdhView.setUint32(42, offset, true);    // Relative offset of local header
      cdh.set(pathBytes, 46);

      centralHeaders.push(cdh);
      offset += lfh.length + size;
    }

    const centralDirStart = offset;
    let centralDirSize = 0;
    for (const cdh of centralHeaders) {
      centralDirSize += cdh.length;
    }

    // 3. End of Central Directory Record (22 字节)
    const eocd = new Uint8Array(22);
    const eocdView = new DataView(eocd.buffer);

    eocdView.setUint32(0, 0x06054b50, true); // EOCD signature
    eocdView.setUint16(4, 0, true);          // Disk number
    eocdView.setUint16(6, 0, true);          // Disk with central dir
    eocdView.setUint16(8, this.files.length, true);  // Entries on this disk
    eocdView.setUint16(10, this.files.length, true); // Total entries
    eocdView.setUint32(12, centralDirSize, true);    // Central dir size
    eocdView.setUint32(16, centralDirStart, true);   // Offset of start of central dir
    eocdView.setUint16(20, 0, true);         // Comment length

    // 组合全部片段
    const totalBytes = offset + centralDirSize + 22;
    const result = new Uint8Array(totalBytes);
    let cur = 0;

    for (const item of localHeaders) {
      result.set(item.lfh, cur);
      cur += item.lfh.length;
      result.set(item.data, cur);
      cur += item.data.length;
    }

    for (const cdh of centralHeaders) {
      result.set(cdh, cur);
      cur += cdh.length;
    }

    result.set(eocd, cur);
    return result;
  }
}
