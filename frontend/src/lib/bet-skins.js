export const MAX_BET_SKINS = 6;

export function toggleBetSkinSelection(selected, skin) {
  if (!skin?.uid) return selected;
  if (selected.some((item) => item.uid === skin.uid)) {
    return selected.filter((item) => item.uid !== skin.uid);
  }
  if (selected.length >= MAX_BET_SKINS) return selected;
  return [...selected, skin];
}
