; Fixed entry points. A browser update rewrites the reset page so that it
; jumps here, and does not rewrite these six bytes. The bodies may move
; inside the resident area; only a full chflash updates the trampolines.

.module iapvec
.area IAPVEC (ABS,CODE)
.org 0x2400
.globl _stub_boot_body
ljmp _stub_boot_body
.org 0x2403
.globl _USB_ISR
ljmp _USB_ISR
