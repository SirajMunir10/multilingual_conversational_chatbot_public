import MarkdownIt from 'markdown-it'

// html: false escapes any HTML in model or user text, so nothing can inject script or markup.
const md = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false })

const defaultLink = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLink(tokens, idx, options, env, self)
}

// Images are never loaded: a reply could be steered into embedding one whose address carries conversation data.
// Only the image's description is shown, as plain text.
md.renderer.rules.image = (tokens, idx) => md.utils.escapeHtml(tokens[idx].content)

export function renderMarkdown(text) {
  return md.render(text || '')
}
