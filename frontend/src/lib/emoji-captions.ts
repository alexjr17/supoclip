// Client-side port of backend/src/emoji_captions.py so the Studio Editor's
// preview and browser export sprinkle the same contextual emojis that the
// backend burns into clips. Keep in sync with the Python module.

const EMOJI_KEYWORD_MAP: Record<string, string> = {
  money: "💰", cash: "💵", dollar: "💵", dollars: "💵", rich: "🤑",
  wealth: "💰", wealthy: "💰", millionaire: "🤑", billionaire: "🤑",
  million: "💰", billion: "💰", profit: "📈", revenue: "📈",
  income: "💵", salary: "💸", price: "🏷️", cost: "💲", free: "🆓",
  invest: "📊", investment: "📊", investing: "📊", stock: "📈",
  stocks: "📈", crypto: "🪙", bitcoin: "₿", business: "💼",
  company: "🏢", startup: "🚀", deal: "🤝", sale: "🛒", buy: "🛒",
  sell: "💸", bank: "🏦", tax: "🧾", taxes: "🧾", budget: "📒",
  save: "🏦", savings: "🏦", debt: "💳", fund: "💰",
  growth: "📈", grow: "📈", growing: "📈", scale: "📊", success: "🏆",
  successful: "🏆", win: "🏆", winning: "🏆", winner: "🥇", won: "🏆",
  goal: "🎯", goals: "🎯", target: "🎯", achieve: "✅", result: "✅",
  results: "✅", best: "🥇", first: "🥇", top: "⬆️", champion: "🏆",
  level: "🆙", upgrade: "⬆️", boost: "🚀", rocket: "🚀",
  idea: "💡", ideas: "💡", think: "🤔", thinking: "🤔", thought: "💭",
  smart: "🧠", genius: "🧠", brain: "🧠", mind: "🧠", learn: "📚",
  learning: "📚", study: "📚", school: "🎓", knowledge: "🧠",
  lesson: "📖", book: "📖", books: "📚", read: "📖", question: "❓",
  answer: "💡", secret: "🤫", truth: "💯", fact: "📌", facts: "💯",
  remember: "🧠", focus: "🎯", discover: "🔍", research: "🔬",
  love: "❤️", loved: "❤️", heart: "❤️", amazing: "🤩", incredible: "🤯",
  insane: "🤯", crazy: "🤯", wow: "😮", shocking: "😱", scary: "😱",
  fear: "😱", happy: "😄", happiness: "😄", sad: "😢", angry: "😡",
  fire: "🔥", hot: "🔥", lit: "🔥", cool: "😎", perfect: "👌",
  beautiful: "😍", favorite: "⭐", epic: "🤩", magic: "✨",
  powerful: "💪", power: "⚡", strong: "💪", energy: "⚡",
  stop: "✋", warning: "⚠️", danger: "⚠️", boom: "💥", explode: "💥",
  time: "⏰", today: "📅", tomorrow: "📅", now: "⏰", fast: "⚡",
  quick: "⚡", quickly: "⚡", instantly: "⚡", minute: "⏰",
  minutes: "⏰", hour: "⏰", hours: "⏰", day: "📅", days: "📅",
  year: "📆", years: "📆", future: "🔮", forever: "♾️", deadline: "⏳",
  people: "👥", team: "🤝", family: "👨‍👩‍👧", friend: "🫂", friends: "🫂",
  everyone: "🙌", everybody: "🙌", you: "👉", audience: "👀",
  followers: "📲", subscribe: "🔔", viral: "📈", famous: "🌟",
  customer: "🛍️", customers: "🛍️", boss: "💼", leader: "🫡",
  work: "💼", working: "💼", hustle: "💪", grind: "💪", effort: "💪",
  hard: "💪", build: "🛠️", building: "🏗️", create: "🎨",
  creating: "🎨", health: "🏥", healthy: "🥗", food: "🍽️", eat: "🍴",
  gym: "🏋️", workout: "🏋️", muscle: "💪", sleep: "😴", water: "💧",
  run: "🏃", running: "🏃",
  ai: "🤖", robot: "🤖", tech: "💻", technology: "💻", computer: "💻",
  phone: "📱", internet: "🌐", online: "🌐", data: "📊", code: "👨‍💻",
  world: "🌍", earth: "🌍", global: "🌍", space: "🚀", science: "🔬",
  game: "🎮", games: "🎮", music: "🎵", video: "🎬", movie: "🎬",
  car: "🚗", house: "🏠", home: "🏠", travel: "✈️", light: "💡",
  key: "🔑",
  // Spanish keywords (keys are accent-folded, so "policía" -> "policia").
  dinero: "💰", plata: "💵", billetes: "💵", cobrar: "💵",
  moneda: "🪙", monedas: "🪙", millones: "💰", rico: "🤑",
  rica: "🤑", pobre: "🪙", venta: "🛒", comprar: "🛒", vender: "💸",
  negocio: "💼", empresa: "🏢", banco: "🏦", impuestos: "🧾",
  ahorrar: "🏦", ahorro: "🏦", deuda: "💳", invertir: "📊",
  inversion: "📊", inversiones: "📊", acciones: "📈",
  cripto: "🪙", ganar: "💰", ganando: "💰", gasto: "💸",
  exito: "🏆", gane: "🏆", ganamos: "🏆", ganaron: "🏆",
  ganador: "🥇", ganadores: "🥇", campeon: "🏆", campeones: "🏆",
  mejor: "🥇", primero: "🥇", primera: "🥇", meta: "🎯",
  objetivo: "🎯", objetivos: "🎯", lograr: "✅", logre: "✅",
  resultado: "✅", resultados: "✅", subir: "⬆️", sube: "⬆️",
  arriba: "⬆️", nivel: "🆙", mejorar: "📈", mejorando: "📈",
  crecer: "📈", creciendo: "📈", crecimiento: "📈", escala: "📊",
  pensar: "🤔", pensando: "🤔",
  penso: "💭", pienso: "💭", mente: "🧠", cerebro: "🧠",
  inteligente: "🧠", genio: "🧠", aprender: "📚", aprendiendo: "📚",
  aprendizaje: "📚", estudiar: "📚", estudio: "📚", estudios: "📚",
  escuela: "🎓", universidad: "🎓", conocimiento: "🧠", leccion: "📖",
  lecciones: "📖", libro: "📖", libros: "📚", leer: "📖",
  pregunta: "❓", preguntas: "❓", respuesta: "💡", respuestas: "💡",
  secreto: "🤫", verdad: "💯", dato: "📌", datos: "📊",
  recuerda: "🧠", recordar: "🧠", enfoque: "🎯", descubrir: "🔍",
  investigacion: "🔬",
  amor: "❤️", amo: "❤️", corazon: "❤️", increible: "🤯",
  loco: "🤯", loca: "🤯", locura: "🤯", miedo: "😱", asustado: "😱",
  feliz: "😄", felices: "😄", felicidad: "😄", contento: "😄",
  triste: "😢", tristeza: "😢", llorar: "😢", enojado: "😡",
  bravo: "😡", fuego: "🔥", caliente: "🔥", genial: "😎",
  perfecto: "👌", perfecta: "👌", hermoso: "😍", hermosa: "😍",
  bella: "😍", belleza: "😍", favorito: "⭐", favorita: "⭐",
  magia: "✨", magico: "✨", poderoso: "💪", poderosa: "💪",
  poder: "⚡", fuerza: "💪", fuerte: "💪", energia: "⚡",
  parar: "✋", cuidado: "⚠️", peligro: "⚠️", peligroso: "⚠️",
  impresionante: "🤩", alucinante: "🤯", exploto: "💥",
  tiempo: "⏰", hoy: "📅", manana: "📅", ahora: "⏰",
  rapido: "⚡", rapida: "⚡", minuto: "⏰", minutos: "⏰",
  hora: "⏰", horas: "⏰", dia: "📅", dias: "📅", ano: "📆",
  anos: "📆", futuro: "🔮", siempre: "♾️", noche: "🌙",
  semana: "📅", semanas: "📅",
  gente: "👥", personas: "👥", familia: "👨‍👩‍👧", amigo: "🫂",
  amiga: "🫂", amigos: "🫂", amigas: "🫂", todos: "🙌",
  todas: "🙌", tu: "👉", audiencia: "👀", seguidores: "📲",
  famoso: "🌟", famosa: "🌟", famosos: "🌟", cliente: "🛍️",
  clientes: "🛍️", jefe: "💼", jefa: "💼", lider: "🫡",
  dios: "🙏", vecino: "🏘️", vecinos: "🏘️", policia: "👮",
  barrio: "🏘️", ciudad: "🏙️", city: "🌃", calle: "🛣️",
  vereda: "🚶", casa: "🏠", vida: "✨",
  trabajo: "💼", trabajar: "💼", trabajando: "💼", trabaja: "💼",
  esfuerzo: "💪", duro: "💪", construir: "🛠️", construyendo: "🏗️",
  crear: "🎨", creando: "🎨", creativo: "🎨", creatividad: "🎨",
  salud: "🏥", comida: "🍽️", comer: "🍴", gimnasio: "🏋️",
  entrenar: "🏋️", entrenando: "🏋️", musculo: "💪", dormir: "😴",
  agua: "💧", correr: "🏃", corriendo: "🏃",
  mundo: "🌍", espacio: "🚀", ciencia: "🔬",
  juego: "🎮", juegos: "🎮", musica: "🎵", cantar: "🎵",
  cancion: "🎵", canciones: "🎵", pelicula: "🎬",
  auto: "🚗", carro: "🚗", hogar: "🏠", viajar: "✈️", viaje: "✈️",
  viajes: "✈️", luz: "💡", llave: "🔑", telefono: "📱",
  celular: "📱", computadora: "💻", computador: "💻",
  graffiti: "🎨", grafiti: "🎨", suerte: "🍀", verano: "☀️",
};

const POWER_WORDS = new Set<string>([
  "never", "always", "everything", "nothing", "everyone", "nobody", "anyone",
  "best", "worst", "most", "biggest", "huge", "massive", "tiny", "every",
  "only", "first", "last", "free", "now", "today", "instantly", "forever",
  "guaranteed", "proven", "secret", "truth", "fact", "literally", "actually",
  "exactly", "must", "need", "stop", "warning", "danger", "critical", "key",
  "important", "remember", "mistake", "wrong", "right", "perfect", "ultimate",
  "powerful", "insane", "crazy", "incredible", "amazing", "shocking", "viral",
  "million", "billion", "thousand", "percent", "double", "triple", "ten",
]);

const NUMBER_RE = /\d/;

const ACCENT_FOLD_MAP: Record<string, string> = {
  á: "a", é: "e", í: "i", ó: "o", ú: "u", ü: "u", ñ: "n",
  Á: "a", É: "e", Í: "i", Ó: "o", Ú: "u", Ü: "u", Ñ: "n",
};

export function normalizeToken(text: string): string {
  return (text || "")
    .toLowerCase()
    .replace(/[áéíóúüñ]/g, (ch) => ACCENT_FOLD_MAP[ch])
    .replace(/[^a-z0-9%]+/g, "");
}

function singularize(token: string): string {
  if (token.length > 4 && token.endsWith("ies")) {
    return `${token.slice(0, -3)}y`;
  }
  if (token.length > 4 && token.endsWith("es") && !token.endsWith("ses")) {
    return token.slice(0, -2);
  }
  if (token.length > 3 && token.endsWith("s") && !token.endsWith("ss")) {
    return token.slice(0, -1);
  }
  return token;
}

function lookupEmoji(token: string): string | null {
  if (!token) return null;
  if (token in EMOJI_KEYWORD_MAP) return EMOJI_KEYWORD_MAP[token];
  const singular = singularize(token);
  if (singular !== token && singular in EMOJI_KEYWORD_MAP) {
    return EMOJI_KEYWORD_MAP[singular];
  }
  return null;
}

export interface EmojiAnnotationOptions {
  enableEmoji?: boolean;
  enableEmphasis?: boolean;
  maxEmojis?: number;
  minWordGap?: number;
  repeatGap?: number;
}

/**
 * Annotate a caption word list with emojis. Returns a Map from word index to
 * the emoji to render right after that word. Mirrors
 * `annotate_caption_words` in backend/src/emoji_captions.py.
 */
export function annotateCaptionWords(
  words: string[],
  options: EmojiAnnotationOptions = {},
): Map<number, string> {
  const {
    enableEmoji = true,
    enableEmphasis = true,
    maxEmojis = 8,
    minWordGap = 3,
    repeatGap = 8,
  } = options;

  const emojiByIndex = new Map<number, string>();
  if (!words.length || !enableEmoji) return emojiByIndex;

  let lastEmojiWord = -(minWordGap + 1);
  const recentEmoji = new Map<string, number>();
  let emojiCount = 0;

  for (let idx = 0; idx < words.length; idx += 1) {
    const token = normalizeToken(words[idx]);
    if (!token) continue;

    const isNumber = NUMBER_RE.test(token);
    const emoji = enableEmoji ? lookupEmoji(token) : null;

    if (enableEmphasis && (emoji || POWER_WORDS.has(token) || isNumber)) {
      // Emphasis is a no-op for the editor preview/export today; kept for
      // parity with the backend annotation pipeline.
    }

    if (!emoji || emojiCount >= maxEmojis) continue;
    if (idx - lastEmojiWord < minWordGap) continue;
    if (idx - (recentEmoji.get(emoji) ?? -(repeatGap + 1)) < repeatGap) continue;

    emojiByIndex.set(idx, emoji);
    lastEmojiWord = idx;
    recentEmoji.set(emoji, idx);
    emojiCount += 1;
  }

  return emojiByIndex;
}
