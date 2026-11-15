import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

type Target = { from: number; to: number } | null;

export const aiTargetKey = new PluginKey<Target>("aiTarget");

// Keeps the passage that the AI is working on visibly selected while the focus is in the
// prompt box (the browser's own selection highlight disappears when the editor loses focus).
export const AiTarget = Extension.create({
  name: "aiTarget",
  addProseMirrorPlugins() {
    return [
      new Plugin<Target>({
        key: aiTargetKey,
        state: {
          init: (): Target => null,
          apply(tr, value): Target {
            const meta = tr.getMeta(aiTargetKey);
            if (meta !== undefined) return meta;
            // Typing elsewhere moves the passage; keep following it.
            return value && tr.docChanged ? { from: tr.mapping.map(value.from), to: tr.mapping.map(value.to) } : value;
          },
        },
        props: {
          decorations(state) {
            const range = aiTargetKey.getState(state);
            return range ? DecorationSet.create(state.doc, [Decoration.inline(range.from, range.to, { class: "ai-target" })]) : null;
          },
        },
      }),
    ];
  },
});
