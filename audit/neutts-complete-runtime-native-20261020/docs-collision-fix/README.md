# Einx documentation collision correction

The complete dependency retry at commit 11f7bb6 stopped during its first installed-file inventory, before any native operation group. The original error was "Installed wheel file bytes changed"; the original generic error did not identify the first rejected wheel member.

Independent checks of the actual 105 wheels and 11 APT Python payloads found one installed-file ownership collision. Einx 0.4.3 and Phonemizer 3.3.0 both contain docs/source/conf.py with different bytes. A single installed path cannot preserve both original payloads.

## Narrow packaging correction

The deterministic Einx derivative moves only docs/source/conf.py to:

einx-0.4.3.data/data/share/doc/einx-0.4.3/source/conf.py

A normal wheel installer places that unchanged document at the isolated environment's share/doc/einx-0.4.3/source/conf.py. Phonemizer retains its original site-packages/docs/source/conf.py. All original Einx payload bytes other than the regenerated RECORD remain unchanged, including runtime code, metadata, WHEEL, licenses, and the moved document itself. No package version, dependency clause, or Python declaration changes. Fixed stored ZIP members make the derivative byte-reproducible without relying on a compressor version.

The original and derivative wheels plus every member identity are retained in the preparation audit's einx-docs directory. The complete lock binds both wheels, the exact relocation and the immutable derivation proof. Preparation reconstructs the derivative from the retained original and requires byte identity with the retained result.

## Verification before retry

Preparation now maps every wheel member and APT payload into one prefix-relative installed namespace. This includes purelib, platlib, data and scripts schemes. It rejects any duplicate file owner, even when the bytes match, and rejects file-versus-parent-directory conflicts. A data-scheme path cannot conceal a collision with site-packages.

The fresh host preparation verifies the original 116 distributions and 183 active dependency links: 105 wheels, 11 original APT Python payloads, the original 122-package foundation, and 20 extra provenance archives. The corrected set has 28,936 unique installed-file targets and zero duplicate owners. The focused host suite passes 25 tests and 48 subtests, including the original real collision, the corrected real pair, deterministic reconstruction, alias rejection, and the unchanged shared installed-file integrity check.

The independent real offline pip installation uses an explicit Android-style Scheme inside a private Windows-host virtual environment. The unchanged shared validators checked 181 original payloads and 188 installed RECORD rows, with two distributions, 186 site files, and both documents at distinct site/share-doc paths. This is installer and byte-provenance evidence; it does not execute Android native package operations. Its original reports, scripts and bounded logs are retained under independent-review/.

Original CI for commit 11f7bb6 is retained separately here: run 39452440980, job 118730512347, 1,262 passed, 84 skipped and 618 subtests passed.

The native validators remain unchanged apart from binding the updated preparer. The next full native retry must still pass actual package operations and native provenance. This correction does not install or import the NeuTTS engine, alter its Python bound, obtain speech weights, admit full speech synthesis, or release a package.
