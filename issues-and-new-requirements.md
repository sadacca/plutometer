## Issues identified: 
1. Too much clutter on righthand panel. 
- Bring the section "Houses equal to target" to the top of the panel
- re-title that section as "How many houses could you buy?" 
- include in this section "geographies selected" and rename this dynamically to the geography level (e.g. Whole Counties if counties are selected or Whole neighborhoods if tracts are selected). 
- Move the rest of the statistics to the end of the panel. 
- Throughout, rename "target value" to "total wealth" 

2. collapsable panel doesn't fully collapse
- use hamburger menu instead of button to collapse panel
- ensure that the removal of the panel allows the display of the map underneath

3. remove target values related to GDP from reference CSV 

4. Title of tool ResVal / Residential Value Choropleth Explorer needs a pithier title e.g. "How rich are the rich, really?"
4. "About this tool" text section is too wordy - needs to be slightly pithier 




## New Requirements: 
1. allow selection of other overlays.  
- If no geographies are selected, display a color gradient (blue to yellow) indicating high to low median house price.  Allow toggling of this display with "total value of residential real-estate" for the geography and no fill.
 
