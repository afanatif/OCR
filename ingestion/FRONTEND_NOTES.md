# Frontend Integration Notes: Medical MCQs

## TailwindCSS & Markdown Rendering
The medical MCQ dataset uses HTML `<sub>` and `<sup>` tags to render complex scientific variables where Unicode subscript characters do not exist. Specifically, the Unicode standard does not include subscript versions of uppercase letters like `A` and `B`, so formulas like `[Na]A` and `[Na]B` are encoded in the JSON as `[Na]<sub>A</sub>` and `[Na]<sub>B</sub>`.

> **TailwindCSS Preflight Issue**
> If your frontend uses TailwindCSS, its default "Preflight" CSS reset strips all native styling from `<sub>` and `<sup>` elements, forcing them to inherit the baseline vertical alignment and font size of the parent text. This will cause subscript tags to render exactly like normal inline text.

### Required CSS Override
To ensure the Markdown renderer displays formulas correctly, you **must** add the following CSS rules to your global stylesheet (or frontend component) to override the Tailwind Preflight:

```css
/* Restore default browser styling for subscripts and superscripts */
sub, sup { 
    font-size: 75%; 
    line-height: 0; 
    position: relative; 
    vertical-align: baseline; 
}
sup { top: -0.5em; }
sub { bottom: -0.25em; }
```

Without this CSS, options like `[Na]<sub>A</sub> = 10[Na]<sub>B</sub>` will appear as `[Na]A = 10[Na]B` in the UI.
