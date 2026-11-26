cmake_minimum_required(VERSION 3.16)
project(airpods-handoff)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Bluetooth DBus Network)

add_executable(airpods-handoff
    main.cpp
    ../native/process_guard.c
    headsetcontrols.cpp
    media/mediacontroller.cpp
)

target_link_libraries(airpods-handoff
    Qt6::Network
    Qt6::Core
    Qt6::Bluetooth
    Qt6::DBus
)

target_include_directories(airpods-handoff PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

install(TARGETS airpods-handoff
    RUNTIME DESTINATION bin
)

enable_testing()
add_executable(test-headset-controls tests/test_headset_controls.cpp headsetcontrols.cpp)
target_include_directories(test-headset-controls PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(test-headset-controls Qt6::Core Qt6::Network)
add_test(NAME headset-controls COMMAND test-headset-controls)
