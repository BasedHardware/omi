import type { IndexedFileType } from '../../shared/types'

const BY_EXT: Record<string, IndexedFileType> = {
  pdf: 'document', doc: 'document', docx: 'document', txt: 'document', md: 'document',
  rtf: 'document', odt: 'document', xls: 'document', xlsx: 'document', csv: 'document',
  ppt: 'document', pptx: 'document',
  ts: 'code', tsx: 'code', js: 'code', jsx: 'code', py: 'code', rs: 'code', go: 'code',
  java: 'code', c: 'code', h: 'code', cpp: 'code', cs: 'code', rb: 'code', php: 'code',
  swift: 'code', kt: 'code', sh: 'code', ps1: 'code', json: 'code', yaml: 'code',
  yml: 'code', toml: 'code', html: 'code', css: 'code', sql: 'code',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', svg: 'image',
  bmp: 'image', tiff: 'image', heic: 'image', ico: 'image',
  mp4: 'media', mov: 'media', avi: 'media', mkv: 'media', webm: 'media', mp3: 'media',
  wav: 'media', flac: 'media', m4a: 'media', aac: 'media',
  zip: 'archive', rar: 'archive', '7z': 'archive', tar: 'archive', gz: 'archive',
  exe: 'application', msi: 'application', lnk: 'application', appx: 'application'
}

// Map a file extension (with or without leading dot, any case) to a category,
// mirroring the macOS FileIndexerService buckets.
export function categorizeExtension(extension: string): IndexedFileType {
  const e = extension.replace(/^\./, '').toLowerCase()
  return BY_EXT[e] ?? 'other'
}
