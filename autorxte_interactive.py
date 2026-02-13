#!/usr/bin/env python3
"""AutoRXTE Interactive Menu - Simple terminal interface"""

import sys
from pathlib import Path

def clear():
    """Clear screen"""
    import os
    os.system('cls' if os.name == 'nt' else 'clear')

def show_menu():
    """Show main menu"""
    print("\n" + "="*60)
    print(" "*15 + "AutoRXTE Interactive")
    print("="*60)
    print("\nCORE WORKFLOW:")
    print("  1) Download data")
    print("  2) Prepare (pcaprepobsid)")
    print("  3) Organize FITS files")
    print("  4) Copy bitmasks")
    print("  5) Create GTI filters")
    print("  6) Extract events")
    print("  7) Generate lightcurves")
    print("  8) Extract spectra")
    print("  9) Generate PDS")
    print("\nADVANCED:")
    print(" 10) Color-color analysis")
    print(" 11) XSPEC fitting")
    print(" 12) Xenon mode workflow")
    print(" 13) Plot lightcurves")
    print("\nOTHER:")
    print(" 14) Run complete workflow")
    print("  0) Exit")
    print("="*60)

def main():
    """Main interactive loop"""
    from autorxte.core import (
        search_and_download, prepare_all_obsids, organize_fits_files,
        copy_bitmask_to_results, create_gti_filters, extract_all_events,
        generate_lightcurves, extract_spectra, compute_pds
    )
    from autorxte.advanced import (
        extract_color_ranges, plot_color_diagrams, fit_all_spectra,
        xenon_complete_workflow, plot_all_lightcurves
    )
    
    while True:
        clear()
        show_menu()
        choice = input("\nChoice: ").strip()
        
        if choice == '0':
            print("\nGoodbye!")
            break
        
        elif choice == '1':
            print("\n--- Download Data ---")
            search_and_download(interactive=True)
        
        elif choice == '2':
            print("\n--- Prepare Observations ---")
            prepare_all_obsids(interactive=True)
        
        elif choice == '3':
            print("\n--- Organize FITS ---")
            organize_fits_files(interactive=True)
        
        elif choice == '4':
            print("\n--- Copy Bitmasks ---")
            copy_bitmask_to_results(interactive=True)
        
        elif choice == '5':
            print("\n--- Create GTI ---")
            create_gti_filters(interactive=True)
        
        elif choice == '6':
            print("\n--- Extract Events ---")
            extract_all_events(interactive=True)
        
        elif choice == '7':
            print("\n--- Generate Lightcurves ---")
            generate_lightcurves(interactive=True)
        
        elif choice == '8':
            print("\n--- Extract Spectra ---")
            extract_spectra(interactive=True)
        
        elif choice == '9':
            print("\n--- Generate PDS ---")
            compute_pds(interactive=True)
        
        elif choice == '10':
            print("\n--- Color-Color Analysis ---")
            extract_color_ranges(interactive=True)
            plot_color_diagrams(interactive=True)
        
        elif choice == '11':
            print("\n--- XSPEC Fitting ---")
            fit_all_spectra(interactive=True)
        
        elif choice == '12':
            print("\n--- Xenon Mode ---")
            xenon_complete_workflow(interactive=True)
        
        elif choice == '13':
            print("\n--- Plot Lightcurves ---")
            plot_all_lightcurves(interactive=True)
        
        elif choice == '14':
            print("\n--- Complete Workflow ---")
            print("\nThis will run all core steps in sequence.")
            if input("Continue? (y/n): ").lower() == 'y':
                search_and_download(interactive=True)
                prepare_all_obsids(interactive=True)
                organize_fits_files(interactive=True)
                copy_bitmask_to_results(interactive=True)
                create_gti_filters(interactive=True)
                extract_all_events(interactive=True)
                generate_lightcurves(interactive=True)
                extract_spectra(interactive=True)
                compute_pds(interactive=True)
                print("\n✓ Complete workflow finished!")
        
        else:
            print("\nInvalid choice!")
        
        input("\nPress Enter to continue...")

if __name__ == '__main__':
    main()
