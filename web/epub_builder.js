/**
 * 纯原生浏览器端 EPUB 3.0 生成器（零依赖，符合 IDPF 国际规范）
 */
import { MiniZip } from './minizip.js';

export function generateEpub(title, author, premise, chapters) {
  const zip = new MiniZip();
  const bookId = 'futuretxt-urn-uuid-' + Date.now();

  // 1. mimetype (必须在首位且无压缩)
  zip.addFile('mimetype', 'application/epub+zip', false, true);

  // 2. META-INF/container.xml
  const containerXml = `<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>`;
  zip.addFile('META-INF/container.xml', containerXml);

  // 3. OEBPS/style.css
  const epubCss = `body {
  font-family: -apple-system, "Songti SC", "SimSun", "Noto Serif CJK SC", serif;
  margin: 5% 8%;
  line-height: 1.85;
  color: #1a1a1a;
  background-color: #fafafa;
}
h1, h2 {
  font-family: "PingFang SC", "Heiti SC", sans-serif;
  text-align: center;
  margin: 1.8em 0 1.2em;
  font-weight: bold;
}
h1 { font-size: 1.8em; }
h2 { font-size: 1.4em; }
p {
  text-indent: 2em;
  margin: 0.6em 0;
  text-align: justify;
}
.cover-desc {
  font-style: italic;
  color: #666;
  text-align: center;
  text-indent: 0;
  margin-top: 2em;
}`;
  zip.addFile('OEBPS/style.css', epubCss);

  // 4. 生成封面与章节 XHTML
  const manifestItems = [
    `<item id="style" href="style.css" media-type="text/css"/>`,
    `<item id="titlepage" href="titlepage.xhtml" media-type="application/xhtml+xml"/>`,
    `<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>`,
    `<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>`,
  ];
  const spineItems = [
    `<itemref idref="titlepage"/>`,
  ];
  const navList = [];
  const ncxNavPoints = [];

  // 扉页
  const titleXhtml = `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
  <title>${escapeXml(title)}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <div style="text-align:center; padding-top: 15%;">
    <h1>${escapeXml(title)}</h1>
    <p style="text-indent:0; font-weight:bold; margin-top:2em;">著：${escapeXml(author || 'FutureTxt 创作者')}</p>
    <p class="cover-desc">${escapeXml(premise || '')}</p>
  </div>
</body>
</html>`;
  zip.addFile('OEBPS/titlepage.xhtml', titleXhtml);

  // 各章节
  chapters.forEach((item, idx) => {
    const chNo = idx + 1;
    const fileId = `chapter_${String(chNo).padStart(3, '0')}`;
    const fileName = `${fileId}.xhtml`;

    manifestItems.push(`<item id="${fileId}" href="${fileName}" media-type="application/xhtml+xml"/>`);
    spineItems.push(`<itemref idref="${fileId}"/>`);
    navList.push(`<li><a href="${fileName}">${escapeXml(item.title)}</a></li>`);
    ncxNavPoints.push(`  <navPoint id="np_${chNo}" playOrder="${chNo + 1}">
    <navLabel><text>${escapeXml(item.title)}</text></navLabel>
    <content src="${fileName}"/>
  </navPoint>`);

    const paras = item.text.split('\n')
      .map(p => p.trim())
      .filter(p => p && !p.startsWith('#'))
      .map(p => `    <p>${escapeXml(p)}</p>`)
      .join('\n');

    const chXhtml = `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
  <title>${escapeXml(item.title)}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <h2>${escapeXml(item.title)}</h2>
${paras}
</body>
</html>`;
    zip.addFile(`OEBPS/${fileName}`, chXhtml);
  });

  // 5. nav.xhtml (EPUB 3 目录)
  const navXhtml = `<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
  <title>目录</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>目录</h1>
    <ol>
      <li><a href="titlepage.xhtml">扉页</a></li>
      ${navList.join('\n      ')}
    </ol>
  </nav>
</body>
</html>`;
  zip.addFile('OEBPS/nav.xhtml', navXhtml);

  // 6. toc.ncx (EPUB 2 兼容回退目录)
  const tocNcx = `<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="${bookId}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>${escapeXml(title)}</text></docTitle>
  <navMap>
    <navPoint id="np_0" playOrder="1">
      <navLabel><text>扉页</text></navLabel>
      <content src="titlepage.xhtml"/>
    </navPoint>
${ncxNavPoints.join('\n')}
  </navMap>
</ncx>`;
  zip.addFile('OEBPS/toc.ncx', tocNcx);

  // 7. content.opf
  const contentOpf = `<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>${escapeXml(title)}</dc:title>
    <dc:creator>${escapeXml(author || 'FutureTxt 创作者')}</dc:creator>
    <dc:identifier id="BookID">${bookId}</dc:identifier>
    <dc:language>zh-CN</dc:language>
    <dc:description>${escapeXml(premise || '')}</dc:description>
    <meta property="dcterms:modified">${new Date().toISOString().replace(/\.[0-9]+Z$/, 'Z')}</meta>
  </metadata>
  <manifest>
    ${manifestItems.join('\n    ')}
  </manifest>
  <spine toc="ncx">
    ${spineItems.join('\n    ')}
  </spine>
</package>`;
  zip.addFile('OEBPS/content.opf', contentOpf);

  return zip.build();
}

function escapeXml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
