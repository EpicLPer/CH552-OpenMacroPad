; Fixed entry points. A browser update rewrites the reset page so that it
; jumps here, and does not rewrite these six bytes. The bodies may move
; inside the resident area; only a full chflash updates the trampolines.
;
; The vector table has to live in this file. SDCC 4.2 emits HOME only from
; the translation unit that contains main, and the USB ISR is resident, so
; the link used to be six bytes at address 0: the reset jump and ljmp _main.
; Startup (mov sp) was then placed at 0x0006, which is inside the interrupt
; table. The hardware USB vector is 0x0043 (0x0003 + 8*INT_NO_USB), not 0x0040.

.module iapvec

.area HOME (CODE)
	ljmp	0x2400		; 0x0000 reset → resident stub
	reti			; 0x0003 INT0
	.ds	7
	reti			; 0x000B TMR0
	.ds	7
	reti			; 0x0013 INT1
	.ds	7
	reti			; 0x001B TMR1
	.ds	7
	reti			; 0x0023 UART0
	.ds	7
	reti			; 0x002B TMR2
	.ds	7
	reti			; 0x0033 SPI0
	.ds	7
	reti			; 0x003B TKEY
	.ds	7
	ljmp	0x2403		; 0x0043 USB → resident ISR trampoline
	.ds	5
	reti			; 0x004B ADC
	.ds	7
	reti			; 0x0053 UART1
	.ds	7
	reti			; 0x005B PWMX
	.ds	7
	reti			; 0x0063 GPIO
	.ds	7
	reti			; 0x006B WDOG
	.ds	7		; HOME continues after 0x0073

.area IAPVEC (ABS,CODE)
.org 0x2400
.globl _stub_boot_body
ljmp _stub_boot_body
.org 0x2403
.globl _USB_ISR
ljmp _USB_ISR
