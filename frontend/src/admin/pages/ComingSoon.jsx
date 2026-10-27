'use client'
import { EmptyState } from '../components/ui'

const PLANNED = {
  knowledge: 'Add, edit and retire articles, upload PDF/DOCX/CSV files, crawl web pages on a schedule, with version history and rollback.',
  translations: 'Side-by-side translation of knowledge and canned replies for every language, with a machine draft you can correct.',
  tuning: 'Edit XO’s instructions, persona, guided journeys, banned topics and tone per language, with a preview of every change.',
  escalation: 'Decide when a conversation goes to a person (keywords, sentiment, low confidence, explicit request, high-value lead) and to which team.',
  experiments: 'Test prompt, flow or tone variants against lead conversion and user satisfaction.',
  rules: 'Change interest rates, loan-to-value limits, debt-burden limits, eligibility thresholds and fees, checked against the approved test cases before they go live.',
  integrations: 'See the health of GRID, Vault, the property feed, OpenAI and ElevenLabs, and choose models. Managing provider keys and connections yourself will follow in a later release.'
}

export default function ComingSoon({ page }) {
  return (
    <EmptyState icon={page.icon} title={`${page.label} is coming in sub-phase ${page.soon}`}>
      {PLANNED[page.id]} ({page.prd})
    </EmptyState>
  )
}
