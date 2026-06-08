The bad pixel mask should be a single-extension FITS file containing integer
values, where 1 indicates a good pixel, 0 indicates a bad pixel, and
2 indicates a reference pixel.

Note that the default files are included in the source repository of this
package, but not in the sdists and wheels from PyPI or GitHub.
They may be downloaded separately, if desired, from the
`SOFIA Redux EXES pipeline reference files <https://doi.org/10.18419/DARUS-5981>__`
dataset at the SOFIA Data Center Astronomy Dataverse or from the
`PIPELINE_REFERENCE directory <https://irsa.ipac.caltech.edu/data/SOFIA/PIPELINE_REFERENCE/EXES/>__`
at IRSA.

Otherwise, the software will attempt to automatically download and
cache the reference file as needed.
