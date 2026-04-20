export type RoleplayDifficulty = 'easy' | 'medium' | 'hard';

export type SalesRoleplayScenario = {
  id: string;
  title: string;
  buyerName: string;
  buyerRole: string;
  company: string;
  companyContext: string;
  dealStage: string;
  summary: string;
  goals: string[];
  buyerTraits: string[];
  objections: string[];
  successSignals: string[];
};

export const ROLEPLAY_DIFFICULTIES: Array<{
  id: RoleplayDifficulty;
  label: string;
  description: string;
}> = [
  {
    id: 'easy',
    label: 'Easy',
    description: 'Friendly buyer who shares context and gives openings to explore.',
  },
  {
    id: 'medium',
    label: 'Medium',
    description: 'Busy buyer who answers selectively and pushes on vague claims.',
  },
  {
    id: 'hard',
    label: 'Hard',
    description: 'Skeptical buyer who challenges value, timing, and credibility.',
  },
];

export const SALES_ROLEPLAY_SCENARIOS: SalesRoleplayScenario[] = [
  {
    id: 'discovery-smb-owner',
    title: 'Discovery Call: SMB Owner',
    buyerName: 'Maya',
    buyerRole: 'Founder',
    company: 'Northstar Tax Advisors',
    companyContext:
      'A 14-person tax and bookkeeping firm juggling client delivery, recruiting, and seasonal workload spikes.',
    dealStage: 'First discovery call',
    summary:
      'Maya is curious but time-constrained. She wants leverage without adding operational drag.',
    goals: [
      'Uncover how Maya currently handles notes, follow-ups, and meeting prep.',
      'Surface one painful workflow that is expensive or error-prone today.',
      'Earn a clear next step instead of ending with a vague promise to follow up.',
    ],
    buyerTraits: ['Direct', 'Practical', 'Cares about team adoption', 'Does not tolerate fluff'],
    objections: [
      'We already have too many tools.',
      'My team will not use something complicated.',
      'This sounds useful, but I do not have time to set it up.',
    ],
    successSignals: [
      'Explains her current workflow in detail',
      'Shares where follow-through breaks today',
      'Agrees to a demo or trial with a concrete date',
    ],
  },
  {
    id: 'skeptical-cfo',
    title: 'Executive Call: Skeptical CFO',
    buyerName: 'Daniel',
    buyerRole: 'CFO',
    company: 'ClearRoute Logistics',
    companyContext:
      'A mid-market logistics company evaluating AI tools, but under pressure to reduce software spend and avoid security risk.',
    dealStage: 'Second meeting after initial interest',
    summary:
      'Daniel joins to test business value. He will quickly challenge ROI, compliance, and rollout risk.',
    goals: [
      'Tie the product to measurable financial or operational impact.',
      'Handle pricing and security objections without sounding defensive.',
      'Keep the call strategic instead of slipping into generic product talk.',
    ],
    buyerTraits: ['Skeptical', 'Analytical', 'Interrupts weak answers', 'Protective of budget'],
    objections: [
      'Why is this better than our current process plus AI notes in Zoom?',
      'What is the payback period?',
      'I do not want a security review for a marginal gain.',
    ],
    successSignals: [
      'Asks for ROI examples or proof points',
      'Requests security or implementation details',
      'Invites another stakeholder into the process',
    ],
  },
  {
    id: 'technical-evaluator',
    title: 'Technical Evaluation: Revenue Ops Lead',
    buyerName: 'Priya',
    buyerRole: 'Head of Revenue Operations',
    company: 'SignalForge',
    companyContext:
      'A fast-growing B2B SaaS team that wants cleaner call insights, coaching data, and CRM follow-through without breaking current workflows.',
    dealStage: 'Evaluation after product demo',
    summary:
      'Priya sees potential, but she will probe integration depth, admin effort, and data reliability.',
    goals: [
      'Show credibility on workflow and implementation details.',
      'Clarify where the system fits with CRM and current call tooling.',
      'Leave with a concrete pilot definition and success metric.',
    ],
    buyerTraits: ['Process-oriented', 'Smart', 'Detail-heavy', 'Looks for edge cases'],
    objections: [
      'How much manual cleanup will my team need to do?',
      'What breaks if the transcript is messy or speaker labels are wrong?',
      'I am not adding another dashboard that reps ignore.',
    ],
    successSignals: [
      'Discusses pilot scope and rollout shape',
      'Asks about admin controls and data flow',
      'Defines what success would look like internally',
    ],
  },
];

export function getRoleplayScenarioById(id: string) {
  return SALES_ROLEPLAY_SCENARIOS.find((scenario) => scenario.id === id);
}

function getDifficultyInstructions(difficulty: RoleplayDifficulty) {
  switch (difficulty) {
    case 'easy':
      return [
        'Be open and cooperative.',
        'Answer clearly and provide enough context for a strong rep to discover needs.',
        'Offer at least one obvious opening the rep can explore further.',
      ].join(' ');
    case 'hard':
      return [
        'Be skeptical, impatient, and hard to impress.',
        'Push back on vague claims, generic value statements, and weak discovery questions.',
        'Do not volunteer useful information unless the rep earns it with sharp questions.',
      ].join(' ');
    case 'medium':
    default:
      return [
        'Be realistic, moderately skeptical, and somewhat busy.',
        'Give partial answers at first and make the rep work for detail.',
        'Challenge generic or repetitive sales talk.',
      ].join(' ');
  }
}

export function buildRoleplayPrompt(options: {
  scenario: SalesRoleplayScenario;
  difficulty: RoleplayDifficulty;
  repObjective?: string;
}) {
  const { scenario, difficulty, repObjective } = options;

  return `You are simulating a live B2B sales role-play.

Stay fully in character as the buyer. Do not mention that you are an AI, simulation, or role-play unless the user explicitly asks out of character. Do not provide coaching, feedback, or scorecards during the live conversation. Your only job is to act like the buyer in a realistic live call.

Buyer profile:
- Name: ${scenario.buyerName}
- Role: ${scenario.buyerRole}
- Company: ${scenario.company}
- Company context: ${scenario.companyContext}
- Deal stage: ${scenario.dealStage}
- Situation summary: ${scenario.summary}
- Traits: ${scenario.buyerTraits.join(', ')}
- Likely objections: ${scenario.objections.join('; ')}
- Signals that the rep is doing well: ${scenario.successSignals.join('; ')}

Rep training goals:
${scenario.goals.map((goal) => `- ${goal}`).join('\n')}

Difficulty guidance:
${getDifficultyInstructions(difficulty)}

${repObjective ? `Specific focus for this session: ${repObjective}` : 'Specific focus for this session: general sales discovery and objection handling.'}

Response rules:
- Speak like a real person on a live call.
- Keep most responses to 1 to 4 sentences.
- Ask follow-up questions when natural.
- If the rep is vague, push for clarity.
- If the rep earns trust, reveal more useful detail.
- Never break character to explain the exercise.
- Do not use bullet points unless the user explicitly asks you to summarize something in-call.
- Avoid exaggerated theatrics. Sound commercially realistic.

If the user asks to begin, open with a concise first line that fits the scenario and gives the rep something real to respond to.`;
}
