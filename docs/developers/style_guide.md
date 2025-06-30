# Style Guide

Docent uses a centralized color system where colors are defined once in `globals.css` and then made available as reusable CSS classes through `tailwind.config.ts`. This ensures consistent colors throughout the application.

## Color Usage Guidelines

### Base Layout Colors
- **`bg-background`** - Main page/app background
- **`bg-secondary`** - Secondary surfaces, sidebars, toolbars

(Unused)
- **`bg-card`** - Card and panel backgrounds
- **`bg-muted`** - Subtle background areas, disabled states

For the default `shadcn` dark/light mode themes, `card`, `secondary`, and `muted` are all the same. For surfaces that need to stand out, we just use `secondary`. This may change in the future.

### Text Colors
- **`text-primary`** - Primary text, body text
- - **`text-muted-foreground`** - Secondary text, captions, metadata
-
(Unused)
- **`text-foreground`** - Important text, headers, emphasis
- **`text-secondary-foreground`** - Text on secondary backgrounds

We just use two colors. `text-primary` is used for headings and emphasis. `text-muted-foreground` is a softer text color used for subheadings.

For body text, choose whatever looks best. A good rule of thumb is to prefer `text-muted-foreground` against `bg-background` and `text-primary` against colors or surfaces -- this just makes the text stand out.

### Borders and Inputs
- **`border-border`** - Standard borders, dividers

(Unused)
- **`ring-ring`** - Focus rings

When you define a border on an element in Tailwind (`border`, `border-x`, etc.), the default color variable is `--border`. If you want a specific border color, you'll need to use both the border side class and a border color class. E.g. `border border-primary/20`.

In dark themes, `--border` is often the same color as `bg-secondary`. For components where we'd like a contrast (e.g button borders), sometimes we use `border-primary/x` where `x` defines some opacity. `border-primary` is usually too contrastive by itself.

We don't use focus rings often, for no particular reason.

### Semantic Colors
Docent includes a full semantic color palette.

- **Blue**: `bg-blue-bg`, `border-blue-border`, `text-blue-text`, `bg-blue-muted`
- **Green**: `bg-green-bg`, `border-green-border`, `text-green-text`, `bg-green-muted`
- **Orange**: `bg-orange-bg`, `border-orange-border`, `text-orange-text`
- **Yellow**: `bg-yellow-bg`, `border-yellow-border`, `text-yellow-text`, `bg-yellow-muted`
- **Red**: `bg-red-bg`, `border-red-border`, `text-red-text`, `bg-red-muted`
- **Indigo**: `bg-indigo-bg`, `border-indigo-border`, `text-indigo-text`, `bg-indigo-muted`
- **Purple**: `bg-purple-bg`, `border-purple-border`, `text-purple-text`

Notes on colors:
- Indigo is used a lot. Primarily as the background color for search results. It's pleasant on light mode, but a bit bright on dark. This might change in the future.
- We use colors in place of semantic class names. E.g. `text-red-text` rather than `text-destructive`, `text-green-text` for play buttons and "okay" statuses, etc.
- Some colors have a `-muted` variant. This is usually just for hover states.
- Sometimes the `-muted` hover state is too bright. This is particularly true in the `TableArea` component where for hovered cells, we just use a low opacity `-text` variant.

## Adding New Colors

We use shadcn's [10 scale color system](https://ui.shadcn.com/colors). Vercel provides a [nice guide](https://vercel.com/geist/colors) for this.

To add new colors to the system:

1. **Define CSS variables in `globals.css`** using HSL values:
   ```css
   :root {
     --my-new-color: 210 100% 50%;        /* Light mode */
     --my-new-color-border: 210 80% 40%;
     --my-new-color-text: 210 80% 40%;
   }

   .dark {
     --my-new-color: 210 60% 20%;         /* Dark mode */
     --my-new-color-border: 210 70% 50%;
     --my-new-color-text: 210 70% 50%;
   }
   ```

   We typically use the same color for `-border` and `-text`. On the 10 scale system, we use `500` for `border` and `text`, and either `950` or `50` for the bg, depending on whether the theme is light or dark. Muted is `200` or `800`.

2. **Register in `tailwind.config.ts`** to create CSS classes:
   ```typescript
   colors: {
     'my-new-color-bg': 'hsl(var(--my-new-color))',
     'my-new-color-border': 'hsl(var(--my-new-color-border))',
     'my-new-color-text': 'hsl(var(--my-new-color-text))',
   }
   ```

3. **Use in components**:
   ```tsx
   <div className="bg-my-new-color-bg border-my-new-color-border text-my-new-color-text">
     Content
   </div>
   ```
