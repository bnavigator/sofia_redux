The dark file should be a raw EXES FITS file, containing reset dark
data appropriate for a particular series.

Note that the default files are not included in the source repository of this
package, or in the sdists and wheels from PyPI or GitHub.
They may be downloaded separately, if desired, from the
`SOFIA Redux EXES pipeline reference files <https://doi.org/10.18419/DARUS-5981>__`
dataset at the SOFIA Data Center Astronomy Dataverse or from the
`PIPELINE_REFERENCE directory <https://irsa.ipac.caltech.edu/data/SOFIA/PIPELINE_REFERENCE/EXES/>__`
at IRSA, and placed into this directory.

Otherwise, the software will attempt to automatically download and
cache the reference file as needed.
