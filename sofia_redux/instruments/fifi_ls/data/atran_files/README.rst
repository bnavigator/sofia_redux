ATRAN data directory
====================

This directory may contain data files for atmospheric correction.

Note that the source code distribution does no longer provide any
ATRAN files. The FIFI-LS reduction pipeline will automatically download
the required ATRAN files from the SOFIA Astronomy Dataverse at DaRUS [1] as
needed. The downloaded files will be placed in the Astropy cache directory
and will be reused for subsequent reductions. Alternatively,
users may download the required ATRAN files manually and provide
the path `atran_dir` in the recipe or place them here.

[1] https://darus.uni-stuttgart.de/dataverse/irs-sofia-ad
