import { InputRule, Node, mergeAttributes } from "@tiptap/core";
import { Paragraph } from "@tiptap/extension-paragraph";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import { AiTarget } from "./ai-highlight";
import StarterKit from "@tiptap/starter-kit";

// {{key}} in a Word template: one unit in the editor, not text. It cannot be half-edited,
// so a typo cannot silently break a placeholder; it is deleted like a single character.
export const Placeholder = Node.create({
  name: "placeholder",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return { key: { default: "" } };
  },

  parseHTML() {
    return [{ tag: "span[data-placeholder]" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, { "data-placeholder": node.attrs.key, class: "ph" }),
      node.attrs.key,
    ];
  },

  // What copy and "selected text" give: back to the {{key}} form the document uses.
  renderText({ node }) {
    return `{{${node.attrs.key}}}`;
  },

  // Typing {{governing_law}} (or pasting it) turns it into a placeholder.
  addInputRules() {
    return [
      new InputRule({
        find: /\{\{\s*([a-z][a-z0-9_]{0,63})\s*\}\}$/,
        handler: ({ state, range, match }) => {
          state.tr.replaceWith(range.from, range.to, this.type.create({ key: match[1] }));
        },
      }),
    ];
  },
});

// A paragraph that is the document's title (Word style "Title").
const TitleParagraph = Paragraph.extend({
  addAttributes() {
    return {
      title: {
        default: false,
        // Enter at the end of the title starts an ordinary paragraph, not a second title.
        keepOnSplit: false,
        parseHTML: (element) => element.hasAttribute("data-title"),
        renderHTML: (attributes) => (attributes.title ? { "data-title": "true", class: "doc-title" } : {}),
      },
    };
  },
});

export const extensions = [
  StarterKit.configure({
    // Word documents in this editor have headings, lists and inline formatting only.
    paragraph: false,
    heading: { levels: [1, 2, 3, 4] },
    orderedList: false,
    blockquote: false,
    code: false,
    codeBlock: false,
    horizontalRule: false,
    strike: false,
    link: false,
  }),
  TitleParagraph,
  Placeholder,
  AiTarget,
  Table.configure({ resizable: false }),
  TableRow,
  TableCell,
  TableHeader, // not used by the editor, but the table schema refers to it
];
