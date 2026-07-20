export type JointRotation = [number, number, number];

export type HandShape = 'OPEN' | 'FIST' | 'POINT' | 'SPLAYED' | 'CURL';

export type Pose = {
  head: JointRotation;
  neck: JointRotation;
  lShoulder: JointRotation;
  lUpperArm: JointRotation;
  lForearm: JointRotation;
  lWrist: JointRotation;
  rShoulder: JointRotation;
  rUpperArm: JointRotation;
  rForearm: JointRotation;
  rWrist: JointRotation;
  spine: JointRotation;
  expression: string; 
  handShape: HandShape;
};

const generateLetterPose = (offset: number): Pose => ({
  head: [0, 0, 0],
  neck: [0, 0, 0],
  lShoulder: [0, 0, 0], lUpperArm: [0.2, 0, 0], lForearm: [0.1, 0, 0], lWrist: [0, 0, 0],
  rShoulder: [0, 0, 0], rUpperArm: [0.5, 0, 0], rForearm: [0.5 + offset, 0, 0], rWrist: [0.2 + offset, 0, 0],
  spine: [0, 0, 0],
  expression: 'NEUTRAL',
  handShape: offset > 0.3 ? 'FIST' : 'POINT',
});

export const SIGN_POSES: Record<string, Pose> = {
  IDLE: {
    head: [0, 0, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0.1, 0, 0], lForearm: [0.1, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [0.1, 0, 0], rForearm: [0.1, 0, 0], rWrist: [0, 0, 0],
    spine: [0, 0, 0],
    expression: 'NEUTRAL',
    handShape: 'OPEN',
  },
  HELLO: {
    head: [0, 0.2, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0.1, 0, 0], lForearm: [0.1, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [1.2, 0, 0], rForearm: [0.8, 0, 0], rWrist: [0.2, 0, 0],
    spine: [0, 0, 0],
    expression: 'SMILE',
    handShape: 'OPEN',
  },
  THANK_YOU: {
    head: [0.3, 0, 0],
    neck: [0.1, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0.1, 0, 0], lForearm: [0.1, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [0.5, 0, 0], rForearm: [0.5, 0, 0], rWrist: [0.5, 0, 0],
    spine: [0.1, 0, 0],
    expression: 'SMILE',
    handShape: 'OPEN',
  },
  YES: {
    head: [0.2, 0, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0.1, 0, 0], lForearm: [0.1, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [0.8, 0, 0], rForearm: [0.8, 0, 0], rWrist: [0, 0, 0],
    spine: [0, 0, 0],
    expression: 'NEUTRAL',
    handShape: 'FIST',
  },
  NO: {
    head: [0, 0, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0.1, 0, 0], lForearm: [0.1, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [1.0, 0, 0], rForearm: [-0.5, 0, 0], rWrist: [0, 0, 0],
    spine: [0, 0, 0],
    expression: 'NEUTRAL',
    handShape: 'SPLAYED',
  },
  I_DONT_KNOW: {
    head: [0, 0, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [1.0, 0, 0], lForearm: [0.5, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [1.0, 0, 0], rForearm: [0.5, 0, 0], rWrist: [0, 0, 0],
    spine: [0, 0, 0],
    expression: 'CONFUSED',
    handShape: 'CURL',
  },
  PLEASE: {
    head: [0.1, 0, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0, 0, 0], lForearm: [0, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [0.6, 0, 0], rForearm: [0.4, 0, 0], rWrist: [0.2, 0, 0],
    spine: [0.2, 0, 0],
    expression: 'SMILE',
    handShape: 'OPEN',
  },
  SORRY: {
    head: [0.4, 0, 0],
    neck: [0.2, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0, 0, 0], lForearm: [0, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [0.8, 0, 0], rForearm: [0.6, 0, 0], rWrist: [0.4, 0, 0],
    spine: [0.3, 0, 0],
    expression: 'SAD',
    handShape: 'FIST',
  },
  GOODBYE: {
    head: [0, 0.1, 0],
    neck: [0, 0, 0],
    lShoulder: [0, 0, 0], lUpperArm: [0, 0, 0], lForearm: [0, 0, 0], lWrist: [0, 0, 0],
    rShoulder: [0, 0, 0], rUpperArm: [1.2, 0, 0], rForearm: [0.5, 0, 0], rWrist: [0.8, 0, 0],
    spine: [0, 0, 0],
    expression: 'SMILE',
    handShape: 'SPLAYED',
  },
};

'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').forEach((char, index) => {
  SIGN_POSES[char] = generateLetterPose(index * 0.1);
});

export function getPoseForGloss(gloss: string): Pose {
  return SIGN_POSES[gloss.toUpperCase()] || SIGN_POSES.IDLE;
}
