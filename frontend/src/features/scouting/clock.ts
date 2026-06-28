// Scouting stores utility timing as seconds elapsed since round start (0–115),
// which is what the model consumes. The UI shows the in-game round clock, which
// starts at 1:55 and counts down, so display/inputs convert: clock = 1:55 
export const ROUND_TIME_S = 115

const clampClock = (v: number) => Math.max(0, Math.min(ROUND_TIME_S, v))

// game-clock "m:ss" 
export function fmtClock(elapsedS: number): string {
  const c = ROUND_TIME_S - clampClock(Math.round(elapsedS || 0))
  return `${Math.floor(c / 60)}:${(c % 60).toString().padStart(2, '0')}`
}

// game-clock text ("1:50" or bare seconds) 
export function parseClock(text: string): number {
  const s = (text || '').trim()
  let clock: number
  if (s.includes(':')) {
    const [m, sec = ''] = s.split(':')
    clock = (parseInt(m, 10) || 0) * 60 + (parseInt(sec, 10) || 0)
  } else {
    clock = parseInt(s, 10) || 0
  }
  return ROUND_TIME_S - clampClock(clock)
}
