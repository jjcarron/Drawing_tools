# Instructions History

1. Initialized repo scaffolding: created virtual environment, requirements, and history file as requested.
2. Added a baseline .gitignore and completed Git initialization after resolving permission issues.
3. Set up a Linux virtual environment at .linux_venv, installed requirements, and added a placeholder generator script for RGBS2VGA_Front_Panel to validate the workflow.
4. Switched the generator to produce a DXF using ezdxf for LibreCAD/QCAD/FreeCAD compatibility, updated requirements, and implemented geometry, axes, dimensions, and title text.
5. Added template selection (defaulting to Templates/iso_en_a4_metric_landscape_aec.dxf) and fit the modelspace content to the sheet layout viewport.
6. Adjusted template fitting to center the drawing within the main viewport (free sheet area) while preserving viewport size and aspect.
7. Centered modelspace geometry inside the free area defined by the border/title block in the template before fitting the layout viewport.
8. Fit the layout viewport to the template border bounds and center the drawing on the full sheet area.
9. Added a SVG-to-DXF conversion tool that seeds standard layers and emits a layer-mapping report.
10. Fixed SVG-to-DXF conversion to flip SVG Y coordinates to DXF space so elements are not vertically inverted.
11. Adjusted SVG path conversion to start relative paths from the flipped origin to avoid vertical sheet duplication.
12. Added inherited SVG text style handling (font-size/font-family) and propagated group styles into DXF text entities and reports.
13. Adjusted SVG-to-DXF text height scaling to a 2.82× factor (2×sqrt(2)).
14. Applied SVG text-anchor alignment (start/middle/end) when placing DXF text to fix centered data fields.
15. Switched centered text alignment to baseline-centered (CENTER/RIGHT) to avoid vertical offsets in QCAD.
16. Added DXF layer lineweights and filled black trimming marks by detecting SVG fill color.
17. Forced geometry entities to use BYLAYER lineweight so QCAD layer edits affect line thickness; kept border/title block thick/thin layers and center at 0.35 mm.
18. Set RGBS2VGA front panel defaults to the A4 ISO5457 DXF template and aligned lineweights/linetypes to QCAD ISO (outline 0.7, dimensions 0.35, axes dash-dot).
19. Updated front panel geometry: circular hole offset to 41.5 mm, added vertical symmetry dimension for openings, and added dimensions for rectangular opening width/height and offsets.
20. Added an AXES layer to the SVG-to-DXF converter so generated templates include a dedicated axes layer for views.
21. Set AXES layer linetype to DASHDOT when available in the DXF.
22. Moved opening position dimensions to the top on a shared level and replaced vertical position dimension with extended symmetry axes.
23. Forced DASHDOT linetype definition for axes even when present in template and applied it directly to axis entities.
24. Replaced vertical position dimension with symmetry axis lines spanning from 2 mm below openings to 2 mm above the plate and placed horizontal offset dimensions on that axis level.
25. Ensured SVG-to-DXF conversion injects a DASHDOT linetype if missing and assigns it to the AXES layer in templates.
26. Updated axes to show four symmetry lines (center horizontal, center vertical, and two vertical through openings) and removed opening position dimensions for later rework.
27. Shortened opening axis bottoms to 2 mm below each opening and placed opening position dimensions on the upper axis level.
28. Added a temporary 100 mm AXES line at sheet center during SVG-to-DXF conversion to help verify axis linetype in QCAD.
29. Made layer setup idempotent so existing template layers (e.g., AXES) are reused and updated instead of raising errors.
30. Prevented template entities from being translated when centering the generated drawing on the sheet.
31. Added a DXF-to-SVG export tool for laser cutting/engraving that outputs selected layers to SVG.
32. Adjusted DXF-to-SVG export to render text with fill color so TEXT layers appear in SVG.
33. Set engrave preset to OUTLINE + TEXT and added text-to-path export for laser-friendly SVGs.
