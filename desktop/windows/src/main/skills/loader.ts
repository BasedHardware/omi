import { app } from 'electron'
import { createHash } from 'crypto'
import { existsSync, readdirSync, readFileSync, statSync, type Dirent } from 'fs'
import { basename, delimiter, dirname, join, relative, resolve } from 'path'
import type { SkillEntry, SkillsListResult } from '../../shared/types'

const MAX_SKILL_DEPTH = 5
const MAX_SKILL_PROMPT_CHARS = 20_000

type SkillRecord = SkillEntry & {
  content: string
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => resolve(value)).filter((value) => value)))
}

function splitEnvPaths(value?: string): string[] {
  if (!value) return []
  return value
    .split(delimiter)
    .map((item) => item.trim())
    .filter(Boolean)
}

function findAncestorSkillRoots(startPath: string): string[] {
  const roots: string[] = []
  let current =
    existsSync(startPath) && statSync(startPath).isFile() ? dirname(startPath) : startPath
  while (current && dirname(current) !== current) {
    const candidate = join(current, '.agents', 'skills')
    if (existsSync(candidate)) roots.push(candidate)
    current = dirname(current)
  }
  return roots
}

export function skillRoots(): string[] {
  const home = app.getPath('home')
  return unique([
    ...splitEnvPaths(process.env.OMI_SKILLS_DIRS),
    ...splitEnvPaths(process.env.OMI_SKILLS_DIR),
    join(home, '.codex', 'skills'),
    join(home, '.agents', 'skills'),
    join(process.resourcesPath, 'skills'),
    ...findAncestorSkillRoots(process.cwd()),
    ...findAncestorSkillRoots(app.getAppPath())
  ]).filter((root) => existsSync(root))
}

function slug(value: string): string {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'skill'
  )
}

function hashPath(value: string): string {
  return createHash('sha1').update(resolve(value)).digest('hex').slice(0, 10)
}

function frontmatterValue(content: string, key: string): string | null {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---/)
  if (!match) return null
  const line = match[1]
    .split(/\r?\n/)
    .find((candidate) => candidate.trim().toLowerCase().startsWith(`${key.toLowerCase()}:`))
  if (!line) return null
  return (
    line
      .slice(line.indexOf(':') + 1)
      .trim()
      .replace(/^['"]|['"]$/g, '') || null
  )
}

function markdownTitle(content: string, fallback: string): string {
  return frontmatterValue(content, 'name') ?? content.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? fallback
}

function markdownDescription(content: string): string {
  const explicit = frontmatterValue(content, 'description')
  if (explicit) return explicit

  const withoutFrontmatter = content.replace(/^---\s*\n[\s\S]*?\n---\s*/, '')
  const lines = withoutFrontmatter.split(/\r?\n/)
  const firstParagraph: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      if (firstParagraph.length > 0) break
      continue
    }
    firstParagraph.push(trimmed)
    if (firstParagraph.join(' ').length > 220) break
  }
  return firstParagraph.join(' ').slice(0, 260)
}

function findSkillFiles(root: string, depth = 0): string[] {
  if (depth > MAX_SKILL_DEPTH) return []
  let entries: Dirent[]
  try {
    entries = readdirSync(root, { withFileTypes: true })
  } catch {
    return []
  }

  const files: string[] = []
  for (const entry of entries) {
    const path = join(root, entry.name)
    if (entry.isFile() && entry.name === 'SKILL.md') {
      files.push(path)
      continue
    }
    if (entry.isDirectory() && !entry.name.startsWith('.')) {
      files.push(...findSkillFiles(path, depth + 1))
    }
  }
  return files
}

function readSkill(root: string, filePath: string): SkillRecord | null {
  try {
    const content = readFileSync(filePath, 'utf8')
    const folder = basename(dirname(filePath))
    const name = markdownTitle(content, folder)
    const relativePath = relative(root, filePath).replace(/\\/g, '/')
    return {
      id: `${slug(name)}-${hashPath(filePath)}`,
      name,
      description: markdownDescription(content),
      sourcePath: filePath,
      relativePath,
      content
    }
  } catch {
    return null
  }
}

function readSkills(): { roots: string[]; records: SkillRecord[] } {
  const roots = skillRoots()
  const byId = new Map<string, SkillRecord>()
  for (const root of roots) {
    for (const filePath of findSkillFiles(root)) {
      const skill = readSkill(root, filePath)
      if (skill) byId.set(skill.id, skill)
    }
  }
  return {
    roots,
    records: Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name))
  }
}

export function listSkills(): SkillsListResult {
  const { roots, records } = readSkills()
  return {
    roots,
    skills: records.map((skill) => ({
      id: skill.id,
      name: skill.name,
      description: skill.description,
      sourcePath: skill.sourcePath,
      relativePath: skill.relativePath
    }))
  }
}

export function loadSkillPromptSections(ids: string[]): string[] {
  const requested = new Set(ids)
  const { records } = readSkills()
  return records
    .filter((skill) => requested.has(skill.id))
    .map((skill) => {
      const content =
        skill.content.length > MAX_SKILL_PROMPT_CHARS
          ? `${skill.content.slice(0, MAX_SKILL_PROMPT_CHARS)}\n\n[skill truncated]`
          : skill.content
      return [`# ${skill.name}`, skill.description, content].filter(Boolean).join('\n\n')
    })
}
